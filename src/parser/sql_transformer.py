from lark import Transformer, v_args, Token, Tree

def _unquote(s: str) -> str:
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        return s[1:-1]
    return s

class SQLTransformer(Transformer):
    def NAME(self, t: Token):
        return str(t)
    
    def STRING(self, t: Token):
        return _unquote(str(t))
    
    def INT(self, t: Token):
        return int(str(t))
    
    def FLOAT(self, t: Token):
        return float(str(t))
    
    @v_args(inline=True)
    def int(self, t):
        # t puede ser Token('INT', '123') o ya un int si algo más lo transformó
        return int(str(t)) if isinstance(t, Token) else int(t)
    
    @v_args(inline=True)
    def float(self, t):
        return float(str(t)) if isinstance(t, Token) else float(t)
    
    @v_args(inline=True)
    def string(self, s):
        # Si llega como Token STRING, descomilla; si ya llega str lo dejo como esta
        return _unquote(str(s)) if isinstance(s, Token) else s
    
    def int_type(self, _):
        return "INT"
    
    def date_type(self, _):
        return "DATE"
    
    @v_args(inline=True)
    def varchar_type(self, size):
        return f"VARCHAR[{size}]"
    
    def array_type(self, _):
        return "ARRAY[FLOAT]"

    # ---------- Index ----------
    @v_args(inline=True)
    def index_spec(self, idx):
        #Con el parche: idx es Token('INDEX_TYPE', 'SEQ'|'BTREE'|'RTREE'|'EHASH'|'ISAM')
        #Sin el parche: a veces llega Tree('index_type', []); intento un fallback.
        if isinstance(idx, Token):
            return str(idx)
        if isinstance(idx, Tree):
            return idx.data.upper()
        return str(idx)

    # ---------- Values / arrays ----------
    def value_list(self, items):
        return items
    
    def number_list(self, items):
        return items

    def array(self, items):
        numbers = items[0] if items else []
        return list(numbers)

    # ---------- Conditions ----------
    @v_args(inline=True)
    def condition(self, *args):
        # Igualdad: (NAME, value)
        if len(args) == 2:
            field, val = args
            return {"op": "=", "field": field, "value": val}
        
        # BETWEEN: (NAME, low, high)
        if len(args) == 3 and not isinstance(args[1], list):
            field, low, high = args
            return {"op": "BETWEEN", "field": field, "low": low, "high": high}
        
        # IN para RTree: (NAME, array, radius)
        if len(args) == 3 and isinstance(args[1], list):
            field, coords, radius = args
            return {"op": "IN", "field": field, "coords": coords, "radius": radius}
        
        return {"op": "unknown", "args": list(args)}

    # ---------- Column defs ----------
    def column_def(self, items):
        # items = [NAME, type_spec, (KEY)?, (index_spec)?]
        name = items[0]
        typ = items[1]
        key = False
        index = None
        for it in items[2:]:
            if isinstance(it, Token) and it.type == "KEY":
                key = True
            elif isinstance(it, str):
                index = it
        return {
            "name": name,
            "type": typ,
            "key": key,
            "index": index,
        }

    # ---------- Statements ----------
    def create_table(self, items):
        table = items[0]
        columns = [it for it in items[1:] if isinstance(it, dict)]
        return {
            "action": "create_table",
            "table": table,
            "columns": columns,
        }

    def create_table_from_file(self, items):
        name = items[0]
        file_path = items[1]
        index_type = str(items[2]).upper()
        index_column = str(items[3])
        return {
            "action": "create_table_from_file",
            "table": name,
            "file": file_path,
            "index_type": index_type,
            "index_column": index_column,
        }

    def insert(self, items):
        table = items[0]
        values = items[1] if len(items) > 1 else []
        return {"action": "insert", "table": table, "values": values}
    
    def delete(self, items):
        table = items[0]
        cond = items[1] if len(items) > 1 else None
        return {
            "action": "delete",
            "table": table,
            "condition": cond
        }
    
    def select(self, items):
        columns = items[0]
        table = items[1]
        cond = items[2] if len(items) > 2 else None
        return {
            "action": "select",
            "table": table,
            "columns": columns,
            "condition": cond,
        }

    def create_index(self, items):
        idx_type, table, column = str(items[0]).upper(), items[1], items[2]
        return {
            "action": "create_index",
            "table": table,
            "index_type": idx_type,
            "column": column
        }

    def drop_index(self, items):
        table, column = items[0], items[1]
        return {
            "action": "drop_index",
            "table": table,
            "column": column
        }

    # ---------- Minor glue ----------
    @v_args(inline=True)
    def number(self, n):
        return n
    
    @v_args(inline=True)
    def value(self, v):
        return v
    
    def column_list(self, items):
        return [str(x) for x in items]
    
    def select_all(self, _):
        return ["*"]
