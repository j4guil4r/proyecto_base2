# src/core/engine.py

import os
import json
import csv
from typing import List, Dict, Any, Generator, Tuple

# Importaciones del núcleo
from src.core.table import Table
from src.core.record import RecordManager

# Importar la interfaz y TODAS las clases de índice
from src.indices.base_index import BaseIndex
from src.indices.bplustree.bplustreeindex import BPlusTreeIndex
from src.indices.hashing.hashingindex import HashIndex
from src.indices.isam.isamindex import ISAMIndex
from src.indices.rtree.rtreeindex import RTreeIndex
# Corregir typo si existe en el nombre del archivo
try:
    from src.indices.sequentialfile.sequentialfileindex import SequentialFileIndex
except ImportError:
    from src.indices.sequentialfile.sequentialfileindex import SequentialFileIndex


# Importar el parser
from src.parser.sqlparser import SQLParser

# Mapeo de nombres de clase para cargar
INDEX_CLASS_MAP = {
    "BPlusTreeIndex": BPlusTreeIndex,
    "HashIndex": HashIndex,
    "ISAMIndex": ISAMIndex,
    "RTreeIndex": RTreeIndex,
    "SequentialFileIndex": SequentialFileIndex,
}

# --- NUEVO: Constante para el orden del B+Tree en experimentos ---
BTREE_ORDER_FOR_EXPERIMENTS = 50 # Probemos con 50

class DatabaseEngine:
    def __init__(self, data_dir: str = 'data'):
        self.data_dir = data_dir
        self.tables: Dict[str, Table] = {}
        self.parser = SQLParser()
        os.makedirs(self.data_dir, exist_ok=True)
        self._load_all_tables()

    def _load_all_tables(self):
        """Escanea el data_dir en busca de metadatos de tablas y las carga."""
        print("Cargando tablas existentes...")
        for filename in os.listdir(self.data_dir):
            # Comprobación más robusta para evitar cargar metadatos de índices
            is_table_meta = (filename.endswith(".meta") and
                             not filename.endswith("_bpt.meta") and
                             not filename.endswith("_hash.meta") and
                             not filename.endswith("_seq.meta") and
                             not filename.endswith("_rtree.meta")) # Asumiendo _rtree.meta no existe

            if is_table_meta:
                table_name = filename.replace(".meta", "")
                try:
                    # Crear instancia de tabla (carga metadata internamente)
                    table = Table(table_name, data_dir=self.data_dir)
                    self.tables[table_name] = table
                    print(f"  - Tabla '{table_name}' cargada.")
                    # Cargar los objetos índice para esta tabla
                    self._load_indexes_for_table(table)
                except Exception as e:
                    print(f"Error al cargar la tabla '{table_name}': {e}")
        print("Carga de tablas finalizada.")

    def _load_indexes_for_table(self, table: Table):
        """Carga los objetos de índice para una tabla ya cargada."""
        # Itera sobre las definiciones de índice guardadas en el .meta de la tabla
        for col_name, index_type in table.index_definitions.items():
            if col_name in table.indexes: continue # Evitar recargar

            try:
                print(f"    - Cargando índice {index_type} en '{table.name}.{col_name}'...")
                IndexClass = INDEX_CLASS_MAP.get(index_type)

                if IndexClass is None:
                    print(f"      ERROR: Tipo de índice desconocido '{index_type}'")
                    continue

                # --- Lógica de inicialización específica por tipo ---
                if index_type == "SequentialFileIndex":
                    # Necesita el record_manager y el índice de la columna clave
                    col_idx = [s[0] for s in table.schema].index(col_name)
                    idx = SequentialFileIndex(
                        table_name=table.name,
                        column_name=col_name,
                        record_manager=table.record_manager, # Pasar el manager de la tabla
                        key_column_index=col_idx,
                        data_dir=self.data_dir
                        # aux_capacity se cargará desde su propio meta si existe, o usará default
                    )
                elif index_type == "ISAMIndex":
                    # ISAM se carga vacío; se construye externamente si es necesario
                    idx = ISAMIndex(
                        table_name=table.name,
                        column_name=col_name,
                        data_dir=self.data_dir
                    )

                # --- MODIFICACIÓN PARA B+TREE ---
                elif index_type == "BPlusTreeIndex":
                    # Pasar el orden definido en la constante
                    idx = BPlusTreeIndex(
                        table_name=table.name,
                        column_name=col_name,
                        data_dir=self.data_dir,
                        order=BTREE_ORDER_FOR_EXPERIMENTS # Usar la constante
                    )
                # --- FIN MODIFICACIÓN ---

                else: # Hash, RTree (constructores simples)
                    # Podrías añadir lógica similar si Hash necesitara bucket_size aquí
                    idx = IndexClass(
                        table_name=table.name,
                        column_name=col_name,
                        data_dir=self.data_dir
                    )

                # Guardar el objeto índice cargado en el diccionario de la tabla
                table.indexes[col_name] = idx

            except Exception as e:
                print(f"      ERROR al cargar el índice '{col_name}': {e}")
                # Considerar si continuar o detenerse si un índice falla al cargar

    def execute(self, sql_string: str) -> (List[Tuple] | str):
        """Punto de entrada principal: Parsea y Ejecuta SQL."""
        try:
            plan = self.parser.parse(sql_string)
            command = plan['command']

            if command == 'CREATE_TABLE':
                return self._handle_create_table(plan)

            if command == 'CREATE_TABLE_FROM_FILE':
                return self._handle_create_from_file(plan)

            if command == 'INSERT':
                return self._handle_insert(plan)

            if command == 'SELECT':
                return self._handle_select(plan)

            if command == 'DELETE':
                return self._handle_delete(plan)

            return f"Comando '{command}' no reconocido."

        except Exception as e:
            # Captura errores del parser o de la ejecución
            print(f"Error de ejecución: {e}")
            # Devolver el mensaje de error al frontend/usuario
            return f"Error: {e}"

    # --- Manejadores de Comandos ---

    def _handle_create_table(self, plan: Dict) -> str:
        table_name = plan['table_name']
        if table_name in self.tables:
            raise ValueError(f"La tabla '{table_name}' ya existe.")

        # Crear instancia de tabla (guarda su propio .meta)
        table = Table(table_name, schema=plan['schema'], data_dir=self.data_dir)
        # Guardar qué índices debe tener esta tabla
        table.index_definitions = plan['index_definitions']
        table._save_metadata() # Actualizar .meta con las definiciones de índices

        # Añadir a tablas en memoria y cargar/crear objetos índice
        self.tables[table_name] = table
        self._load_indexes_for_table(table) # Crea los archivos .meta/.dat de los índices

        return f"Tabla '{table_name}' creada exitosamente."

    def _handle_create_from_file(self, plan: Dict) -> str:
        """Maneja 'CREATE TABLE ... FROM FILE ...'"""
        table_name = plan['table_name']
        if table_name not in self.tables:
            # Esta sintaxis requiere que la tabla ya exista (con CREATE TABLE ...)
            raise ValueError(f"Tabla '{table_name}' no existe. Defina el esquema primero con CREATE TABLE (...).")

        table = self.tables[table_name]
        file_path = plan['from_file']

        # Verificar si el archivo CSV existe
        if not os.path.exists(file_path):
             raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

        # Lógica especial para construir ISAM estáticamente DESPUÉS de cargar datos
        isam_col = None
        for col, idx_type in table.index_definitions.items():
            if idx_type == "ISAMIndex":
                isam_col = col
                break # Asumir solo un ISAM por tabla por ahora

        # Cargar datos e indexar dinámicamente (excepto ISAM)
        print(f"Cargando datos desde '{file_path}' en '{table_name}'...")
        count = 0
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            try:
                header = next(reader) # Asumir que hay cabecera
            except StopIteration:
                return "Archivo CSV vacío." # No hacer nada si está vacío

            for row in reader:
                if not row: continue
                try:
                    # Convertir valores al tipo correcto según el esquema
                    values = self._cast_row_values(row, table.schema)
                    # Insertar en la tabla y en los índices (excepto ISAM si existe)
                    self._insert_record_into_table(table, values, skip_isam=bool(isam_col))
                    count += 1
                except ValueError as e:
                    print(f"  Advertencia: Saltando fila debido a error de conversión: {e} - Fila: {row}")
                except Exception as e:
                    print(f"  Error inesperado procesando fila {row}: {e}")

        # Si había un ISAM definido, construirlo ahora con todos los datos cargados
        if isam_col:
            print(f"Construyendo índice ISAM estático en '{isam_col}'...")
            try:
                # build_from_table leerá los datos del .dat de la tabla
                idx = ISAMIndex.build_from_table(table, isam_col)
                table.indexes[isam_col] = idx # Reemplazar el objeto vacío cargado antes
            except Exception as e:
                 print(f"ERROR al construir índice ISAM para '{isam_col}': {e}")


        return f"{count} registros procesados e insertados en '{table_name}'."

    def _handle_insert(self, plan: Dict) -> str:
        """Maneja 'INSERT INTO ... VALUES ...'"""
        table_name = plan['table_name']
        table = self.tables.get(table_name)
        if not table:
            raise ValueError(f"Tabla '{table_name}' no encontrada.")

        # Convertir valores del plan a tipos correctos
        values = self._cast_row_values(plan['values'], table.schema)

        # Usar la función helper para insertar en tabla e índices
        self._insert_record_into_table(table, values)

        return "1 registro insertado."

    def _insert_record_into_table(self, table: Table, values: List[Any], skip_isam: bool = False):
        """Función helper para inserción (usada por INSERT y CREATE FROM FILE)."""

        # 1. Insertar en el archivo de datos principal (.dat de la tabla)
        rid = table.insert_record(values)

        # 2. Insertar en todos los índices definidos y cargados
        for col_name, index_obj in table.indexes.items():
            # Saltar ISAM durante la carga masiva si se va a construir después
            if skip_isam and isinstance(index_obj, ISAMIndex):
                continue

            # Obtener la clave de la columna correspondiente
            col_idx = [s[0] for s in table.schema].index(col_name)
            key = values[col_idx]

            # El SequentialFile es especial: quiere el registro completo como 'value'
            if isinstance(index_obj, SequentialFileIndex):
                index_obj.add(key, values) # key es redundante aquí pero lo pasamos
            else:
                # B+, Hash, ISAM (inserciones post-build), RTree quieren el RID
                index_obj.add(key, rid)

    def _handle_select(self, plan: Dict) -> List[Tuple]:
        """Maneja 'SELECT * FROM ...'"""
        table_name = plan['table_name']
        table = self.tables.get(table_name)
        if not table:
            raise ValueError(f"Tabla '{table_name}' no encontrada.")

        where = plan['where']

        # --- Caso 1: No hay WHERE (Full Table Scan) ---
        if not where:
            # print(f"Ejecutando Full Table Scan en '{table_name}'...")
            # table.scan() devuelve (rid, record), solo queremos el record
            return [record for rid, record in table.scan()]

        # --- Caso 2: Hay WHERE ---
        col = where['column']

        # --- Caso 2a: No hay índice en la columna (Full Table Scan con Filtro) ---
        if col not in table.indexes:
            # print(f"Ejecutando Full Table Scan (filtro en '{col}') en '{table_name}'...")
            results = []
            try:
                col_idx = [s[0] for s in table.schema].index(col)
            except ValueError:
                 raise ValueError(f"Columna '{col}' no encontrada en la tabla '{table_name}'.")

            op = where['op']
            value = where.get('value')
            value1 = where.get('value1')
            value2 = where.get('value2')

            for rid, record in table.scan():
                record_value = record[col_idx]
                match = False
                if op == '=' and record_value == value:
                    match = True
                elif op == 'BETWEEN' and value1 <= record_value <= value2:
                    match = True
                # Añadir más operadores si se implementan en el parser (>, <, etc.)

                if match:
                    results.append(record)
            return results

        # --- Caso 2b: Hay índice en la columna (Index Scan) ---
        # print(f"Ejecutando Index Scan en '{table_name}.{col}'...")
        index_obj = table.indexes[col]
        op = where['op']
        rids_or_records = [] # El índice puede devolver RIDs o registros

        try:
            if op == '=':
                rids_or_records = index_obj.search(where['value'])
            elif op == 'BETWEEN':
                # Asegurarse de que el índice soporta rangeSearch
                if not hasattr(index_obj, 'rangeSearch'):
                     raise NotImplementedError(f"rangeSearch no soportado por índice en '{col}'")
                rids_or_records = index_obj.rangeSearch(where['value1'], where['value2'])
            elif op == 'IN' and isinstance(index_obj, RTreeIndex):
                 # Asegurarse de que el índice soporta radius_search
                if not hasattr(index_obj, 'radius_search'):
                     raise NotImplementedError(f"radius_search no soportado por índice en '{col}'")
                rids_or_records = index_obj.radius_search(where['point'], where['radius'])
            else:
                 raise ValueError(f"Operación '{op}' no soportada por el índice en '{col}'.")
        except NotImplementedError:
             # Si el índice no soporta la operación (ej. rangeSearch en Hash), recurrir a Scan
             print(f"  Advertencia: Operación '{op}' no soportada por el índice. Recurriendo a Full Table Scan.")
             return self._handle_select({'command': 'SELECT', 'table_name': table_name, 'where': None}) # Rehacer como scan

        # --- Post-procesamiento: Obtener registros si el índice devolvió RIDs ---
        if isinstance(index_obj, SequentialFileIndex):
            # SequentialFile ya devuelve los registros completos
            return rids_or_records
        else:
            # B+, Hash, ISAM, RTree devuelven RIDs (List[int])
            results = []
            for rid in rids_or_records:
                try:
                    record = table.get_record(rid)
                    if record: # Asegurarse de que el registro aún existe
                        results.append(record)
                except IndexError:
                     print(f"  Advertencia: RID {rid} del índice no encontrado en la tabla (posible inconsistencia).")
            return results

    def _handle_delete(self, plan: Dict) -> str:
        """Maneja 'DELETE FROM ... WHERE ...' (solo igualdad por ahora)"""
        table_name = plan['table_name']
        table = self.tables.get(table_name)
        if not table:
            raise ValueError(f"Tabla '{table_name}' no encontrada.")

        where = plan['where']
        col = where['column']
        value_to_delete = where['value']

        # Requiere índice en la columna para DELETE eficiente
        if col not in table.indexes:
            raise ValueError(f"DELETE requiere un índice en la columna '{col}'. No se soporta Full Table Scan para DELETE.")

        index_to_use = table.indexes[col]

        # --- Caso Especial: SequentialFile ---
        if isinstance(index_to_use, SequentialFileIndex):
            print(f"Iniciando reconstrucción para DELETE en SequentialFile '{col}'...")
            # remove() ya reconstruye el archivo principal y limpia el auxiliar
            # Devuelve los registros que *estaban* antes de borrar
            deleted_records = index_to_use.remove(value_to_delete, None)
            count = len(deleted_records)

            # ¡CRÍTICO! Debemos reconstruir TODOS los otros índices usando el .dat actualizado
            print("Reconstruyendo todos los otros índices...")
            schema_cols = [s[0] for s in table.schema]
            for other_col, other_idx in table.indexes.items():
                if other_col == col: continue # Saltar el índice que ya se reconstruyó

                print(f"  Reconstruyendo índice en '{other_col}'...")
                # Crear una nueva instancia vacía del índice
                NewIndexClass = INDEX_CLASS_MAP[table.index_definitions[other_col]]
                
                # Pasar argumentos específicos si es necesario (ej. order para B+)
                new_idx_args = {'table_name': table.name, 'column_name': other_col, 'data_dir': self.data_dir}
                if isinstance(other_idx, BPlusTreeIndex):
                    new_idx_args['order'] = other_idx.tree.order # Mantener el orden original
                # Añadir otros args si son necesarios (ej. bucket_size para Hash)
                
                new_idx = NewIndexClass(**new_idx_args)
                
                # Repoblar el nuevo índice escaneando el .dat actualizado
                other_col_idx = schema_cols.index(other_col)
                # table.scan() leerá el archivo .dat reconstruido por SequentialFile.remove
                for rid, record in table.scan():
                    key = record[other_col_idx]
                    if isinstance(new_idx, SequentialFileIndex): # Imposible aquí, pero por si acaso
                         new_idx.add(key, list(record))
                    else:
                         new_idx.add(key, rid)
                
                # Reemplazar el índice antiguo por el reconstruido
                table.indexes[other_col] = new_idx
                # Importante: Guardar metadata si aplica (ej. B+)
                if hasattr(new_idx, 'tree') and hasattr(new_idx.tree, 'save_meta'):
                    new_idx.tree.save_meta()
                elif hasattr(new_idx, 'directory') and hasattr(new_idx.directory, 'save'):
                     new_idx.directory.save()
                # ISAM no necesita save aquí

            return f"{count} registros eliminados (reconstrucción completa)."

        # --- Eliminación estándar (B+, Hash, ISAM, RTree) ---
        # 1. Encontrar RIDs usando el índice de la cláusula WHERE
        rids_to_delete = index_to_use.search(value_to_delete)
        count = 0
        schema_cols = [s[0] for s in table.schema]

        # 2. Para cada RID, obtener el registro completo (para otras claves)
        for rid in rids_to_delete:
            try:
                record = table.get_record(rid)
                if not record: continue # Registro ya no existe?

                # 3. Eliminar la entrada (key, rid) de CADA índice de la tabla
                for col_name, index_obj in table.indexes.items():
                    col_idx = schema_cols.index(col_name)
                    key = record[col_idx]
                    try:
                        # Llamar a remove con el RID específico
                        index_obj.remove(key, rid)
                    except Exception as e:
                         print(f"  Advertencia: Error eliminando de índice '{col_name}' para RID {rid}: {e}")
                count += 1
            except IndexError:
                 print(f"  Advertencia: RID {rid} del índice no encontrado en tabla durante DELETE.")


        # Nota: Los datos en .dat quedan "huérfanos". Esto es aceptable.
        return f"{count} registros eliminados."


    def _cast_row_values(self, row: List[str | Any], schema: List[Tuple]) -> List[Any]:
        """Convierte una fila (de CSV o INSERT) a tipos de Python según el esquema."""
        if len(row) != len(schema):
            raise ValueError(f"Conteo de columnas incorrecto. Se esperaban {len(schema)} pero se recibieron {len(row)}.")

        casted_values = []
        for i, (col_name, col_type, length) in enumerate(schema):
            # El valor puede ya estar casteado si viene del parser directo
            value = row[i]
            expected_type = None
            target_type_str = col_type # Para mensaje de error

            try:
                if col_type == 'INT':
                    expected_type = int
                    casted_values.append(int(value))
                elif col_type == 'FLOAT':
                    expected_type = float
                    casted_values.append(float(value))
                elif col_type == 'ARRAY[FLOAT]':
                    target_type_str = "tuple(float, float,...)"
                    if isinstance(value, str): # Si viene de CSV
                        coords = value.strip('()').split(',')
                        casted_values.append(tuple(float(c.strip()) for c in coords))
                    elif isinstance(value, tuple): # Si viene directo del parser
                        casted_values.append(value)
                    else:
                        raise TypeError("Se esperaba string o tupla para ARRAY[FLOAT]")
                else: # VARCHAR, DATE, etc. se tratan como string
                    expected_type = str
                    casted_values.append(str(value))

            except (ValueError, TypeError) as e:
                err_msg = f"Error al convertir valor '{value}' ({type(value).__name__}) para columna '{col_name}' ({target_type_str})"
                if expected_type:
                    err_msg += f", se esperaba {expected_type.__name__}"
                raise ValueError(f"{err_msg}: {e}")
            except Exception as e:
                # Captura otros errores inesperados
                 raise ValueError(f"Error inesperado al convertir valor '{value}' para columna '{col_name}': {e}")

        return casted_values