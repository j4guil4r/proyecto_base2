# src/parser/sqlparser.py
# ... (importaciones y __init__ sin cambios) ...
import re
# shlex ya no es necesario para _parse_insert
from typing import Dict, Any

class SQLParser:
    # ... (__init__, parse, _parse_create sin cambios) ...
    def __init__(self):
        self.re_create = re.compile(r"CREATE TABLE (\w+)\s*\((.*?)\)", re.IGNORECASE | re.DOTALL)
        self.re_create_from_file = re.compile(r"CREATE TABLE (\w+) FROM FILE \"(.*?)\"", re.IGNORECASE)
        self.re_insert = re.compile(r"INSERT INTO (\w+) VALUES\s*\((.*?)\)", re.IGNORECASE | re.DOTALL)
        self.re_select = re.compile(r"SELECT \* FROM (\w+)(?:\s+WHERE\s+(.*))?", re.IGNORECASE)
        self.re_delete = re.compile(r"DELETE FROM (\w+) WHERE (.*)", re.IGNORECASE)

    def parse(self, sql: str) -> Dict[str, Any]:
        sql = sql.strip().rstrip(';')
        match = self.re_create.fullmatch(sql)
        if match: return self._parse_create(match.group(1), match.group(2))
        match = self.re_create_from_file.fullmatch(sql)
        if match: return {'command': 'CREATE_TABLE_FROM_FILE', 'table_name': match.group(1), 'from_file': match.group(2)}
        match = self.re_insert.fullmatch(sql)
        if match: return self._parse_insert(match.group(1), match.group(2))
        match = self.re_select.fullmatch(sql)
        if match: return self._parse_select(match.group(1), match.group(2))
        match = self.re_delete.fullmatch(sql)
        if match: return self._parse_delete(match.group(1), match.group(2))
        raise ValueError(f"Consulta SQL no válida o no soportada: {sql}")

    def _parse_create(self, table_name: str, schema_str: str) -> Dict[str, Any]:
        plan = {'command': 'CREATE_TABLE', 'table_name': table_name, 'schema': [], 'index_definitions': {}}
        col_defs = [col.strip() for col in schema_str.split(',')]
        for col_def in col_defs:
            if not col_def: continue
            parts = col_def.split()
            if len(parts) < 2: raise ValueError(f"Definición de columna inválida: '{col_def}'")
            col_name = parts[0]; col_type_full = parts[1]; col_type = ""; length = 0
            if '[' in col_type_full and col_type_full.upper().startswith('VARCHAR'):
                match = re.match(r"VARCHAR\[(\d+)\]", col_type_full, re.IGNORECASE)
                if not match: raise ValueError(f"Formato VARCHAR inválido: '{col_type_full}'")
                col_type = 'VARCHAR'; length = int(match.group(1))
            elif col_type_full.upper() == 'ARRAY[FLOAT]':
                col_type = 'ARRAY[FLOAT]'; length = 16
            elif col_type_full.upper() == 'INT': col_type = 'INT'; length = 4
            elif col_type_full.upper() == 'FLOAT': col_type = 'FLOAT'; length = 8
            else: col_type = col_type_full.upper(); length = 0; print(f"Advertencia: Tipo '{col_type}' no completamente especificado.")
            plan['schema'].append((col_name, col_type, length))
            index_type_str = None
            if 'INDEX' in col_def.upper():
                 index_keyword_pos = col_def.upper().find('INDEX')
                 remaining_parts = col_def[index_keyword_pos:].split()
                 if len(remaining_parts) > 1: index_type_str = remaining_parts[1]
            if index_type_str:
                type_map = {'BTREE': 'BPlusTreeIndex', 'HASH': 'HashIndex', 'ISAM': 'ISAMIndex', 'SEQ': 'SequentialFileIndex', 'RTREE': 'RTreeIndex'}
                plan['index_definitions'][col_name] = type_map.get(index_type_str.upper(), index_type_str)
        return plan


    # --- INICIO CORRECCIÓN MANUAL PARSE INSERT ---
    def _parse_insert(self, table_name: str, values_str: str) -> Dict[str, Any]:
        """Parsea los valores en INSERT (Enfoque Manual)."""
        plan = {
            'command': 'INSERT',
            'table_name': table_name,
            'values': []
        }
        values = []
        current_value = ""
        in_quotes = None # Almacena el carácter de comilla (' o ")
        paren_level = 0
        
        for char in values_str:
            # Manejo de Comillas
            if char == "'" or char == '"':
                if in_quotes == char: # Comilla de cierre
                    in_quotes = None
                    current_value += char # Incluir la comilla en el valor
                elif in_quotes is None: # Comilla de apertura
                    in_quotes = char
                    current_value += char # Incluir la comilla
                else: # Comilla dentro de otra comilla (ignorar por ahora)
                    current_value += char
            # Manejo de Paréntesis (solo si no estamos dentro de comillas)
            elif char == '(' and in_quotes is None:
                paren_level += 1
                current_value += char
            elif char == ')' and in_quotes is None:
                paren_level -= 1
                current_value += char
            # Manejo de Coma Separadora (solo si no estamos en comillas ni paréntesis)
            elif char == ',' and in_quotes is None and paren_level == 0:
                values.append(current_value.strip())
                current_value = "" # Reiniciar para el siguiente valor
            # Otros caracteres
            else:
                current_value += char

        # Añadir el último valor acumulado
        values.append(current_value.strip())

        # Convertir a tipos de Python
        plan['values'] = [self._cast_value(v) for v in values]
        return plan
    # --- FIN CORRECCIÓN MANUAL PARSE INSERT ---


    # ... (_parse_select, _parse_delete, _cast_value sin cambios desde la última versión) ...
    def _parse_select(self, table_name: str, where_str: str | None) -> Dict[str, Any]:
        plan = {'command': 'SELECT', 'table_name': table_name, 'where': None}
        if not where_str: return plan
        match = re.match(r"(\w+) BETWEEN (.*) AND (.*)", where_str, re.IGNORECASE)
        if match:
            plan['where'] = {'column': match.group(1), 'op': 'BETWEEN', 'value1': self._cast_value(match.group(2)), 'value2': self._cast_value(match.group(3))}
            return plan
        match = re.match(r"(\w+) IN \(\((.*?)\),\s*(.*?)\)", where_str, re.IGNORECASE)
        if match:
            try:
                point = tuple(float(p.strip()) for p in match.group(2).split(','))
                radius = float(match.group(3).strip())
            except ValueError: raise ValueError(f"Formato inválido R-Tree IN: '({match.group(2)}), {match.group(3)}'")
            plan['where'] = {'column': match.group(1), 'op': 'IN', 'point': point, 'radius': radius}
            return plan
        match = re.match(r"(\w+)\s*=\s*(.*)", where_str, re.IGNORECASE)
        if match:
            plan['where'] = {'column': match.group(1), 'op': '=', 'value': self._cast_value(match.group(2))}
            return plan
        raise ValueError(f"Cláusula WHERE no soportada: {where_str}")

    def _parse_delete(self, table_name: str, where_str: str) -> Dict[str, Any]:
        match = re.match(r"(\w+)\s*=\s*(.*)", where_str, re.IGNORECASE)
        if not match: raise ValueError(f"Cláusula WHERE para DELETE no soportada: {where_str}")
        return {'command': 'DELETE', 'table_name': table_name, 'where': {'column': match.group(1), 'op': '=', 'value': self._cast_value(match.group(2))}}

    def _cast_value(self, value: str) -> Any:
        value = value.strip()
        # String (entre comillas) - Asegurarse de que _parse_insert las incluya
        if (value.startswith("'") and value.endswith("'")) or \
           (value.startswith('"') and value.endswith('"')):
            return value[1:-1]
        # Tupla (para RTree) - Asegurarse de que _parse_insert las incluya
        if value.startswith('(') and value.endswith(')'):
            try: return tuple(float(p.strip()) for p in value.strip('()').split(','))
            except ValueError: return value # Devolver como string si falla
        # Float
        try: return float(value)
        except ValueError: pass
        # Int
        try: return int(value)
        except ValueError: pass
        # Devolver como string si todo falla (ej. si era una tupla mal formada)
        return value