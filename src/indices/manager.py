# src/indices/manager.py
from __future__ import annotations
from typing import Dict, List, Tuple, Any, Optional

from .base_index import BaseIndex
from .bplustree.bplustreeindex import BPlusTreeIndex
from .hashing.hashingindex import HashIndex as EHHashIndex
from .isam.isamindex import ISAMIndex
from .rtree.rtreeindex import RTreeIndex
from .sequentialfile.sequentialfileindex import SequentialFileIndex

class IndexManager:
    """
    Administra índices por tabla/columna.
    - create_index / rebuild_all
    - on_insert (actualiza índices)
    - probes de búsqueda para SELECT (=, BETWEEN, IN)
    """
    def __init__(self):
        # índices vivos: {table: {column: BaseIndex}}
        self._indexes: Dict[str, Dict[str, BaseIndex]] = {}
        # specs para reconstrucción: {table: [(column, type_str)]}
        self._specs: Dict[str, List[Tuple[str, str]]] = {}

    def list_for_table(self, table_name: str) -> Dict[str, BaseIndex]:
        return self._indexes.get(table_name, {})

    def declare(self, table_name: str, column: str, idx_type: str):
        specs = self._specs.setdefault(table_name, [])
        if (column, idx_type) not in specs:
            specs.append((column, idx_type))

    def create_index(self, table, column: str, idx_type: str):
        """Construye el índice desde los datos en disco."""
        self.declare(table.name, column, idx_type)
        if table.name not in self._indexes:
            self._indexes[table.name] = {}

        pos = {n: i for i,(n,_t,_l) in enumerate(table.schema)}[column]

        if idx_type == "EHASH":
            idx = EHHashIndex(table.name, column, data_dir=table.data_dir)
            for rid, values in table.scan() or []:
                idx.add(values[pos], rid)
            self._indexes[table.name][column] = idx
            return

        if idx_type == "BTREE":
            idx = BPlusTreeIndex(table.name, column, data_dir=table.data_dir)
            for rid, values in table.scan() or []:
                idx.add(values[pos], rid)
            if hasattr(idx, "persist"):
                idx.persist()
            self._indexes[table.name][column] = idx
            return

        if idx_type == "ISAM":
            idx = ISAMIndex.build_from_table(table, column)
            self._indexes[table.name][column] = idx
            return

        if idx_type == "SEQ":
            idx = SequentialFileIndex(
                table_name=table.name,
                column_name=column,
                record_manager=table.record_manager,
                key_column_index=pos,
                data_dir=table.data_dir,
                aux_capacity=10
            )
            for _rid, values in table.scan() or []:
                idx.add(values[pos], list(values))
            self._indexes[table.name][column] = idx
            return

        if idx_type == "RTREE":
            idx = RTreeIndex(table.name, column, data_dir=table.data_dir)
            for rid, values in table.scan() or []:
                coords = self._parse_coords(values[pos])
                if coords is not None:
                    idx.add(coords, rid)
            self._indexes[table.name][column] = idx
            return

        raise ValueError(f"Tipo de índice no soportado: {idx_type}")
    
    def drop_index(self, table, column: str):
        if table.name in self._indexes:
            self._indexes[table.name].pop(column, None)
            if not self._indexes[table.name]:
                self._indexes.pop(table.name, None)
        # quita spec para no reconstruir
        specs = self._specs.get(table.name, [])
        self._specs[table.name] = [(c,t) for (c,t) in specs if c != column]
        # Borrar archivos en disco TODO (?)


    def rebuild_all(self, table) -> None:
        """Reconstruye todos los índices declarados para la tabla desde cero."""
        specs = self._specs.get(table.name) or getattr(table, "index_specs", [])
        if not specs:
            self._indexes.pop(table.name, None)
            return

        # Limpia el mapa en memoria y re-crea cada índice
        self._indexes[table.name] = {}
        for col, typ in specs:
            self.create_index(table, col, typ)
        # Nada de persist aquí: create_index ya lo hizo.


    def on_insert(self, table, rid: int, values: List[Any]) -> None:
        """Actualiza todos los índices con el nuevo registro."""
        idxs = self._indexes.get(table.name)
        if not idxs:
            return
        name_pos = {n: i for i,(n,_t,_l) in enumerate(table.schema)}
        for col, idx in idxs.items():
            p = name_pos[col]
            if isinstance(idx, SequentialFileIndex):
                idx.add(values[p], list(values))
            elif isinstance(idx, RTreeIndex):
                coords = self._parse_coords(values[p])
                if coords is not None:
                    idx.add(coords, rid)
            else:
                idx.add(values[p], rid)

    # -------- Probes para el planner muy básico --------

    def probe_eq(self, table_name: str, column: str, value: Any):
        """Devuelve (kind, payload):
           kind='records' => payload es lista de registros completos
           kind='rids'    => payload es lista de rids
           kind=None      => no hay índice usable
        """
        idx = self._indexes.get(table_name, {}).get(column)
        if not idx:
            return None, None
        # SeqFile devuelve registros, no rids
        if isinstance(idx, SequentialFileIndex):
            return 'records', idx.search(value)
        # Hash, B+Tree, ISAM devuelven rids
        return 'rids', idx.search(value)

    def probe_between(self, table_name: str, column: str, low: Any, high: Any):
        idx = self._indexes.get(table_name, {}).get(column)
        if not idx or not hasattr(idx, "rangeSearch"):
            return None, None
        try:
            res = idx.rangeSearch(low, high)
        except NotImplementedError:
            return None, None
        # Secuencial puede devolver registros
        if res and isinstance(res[0], list):
            return 'records', res
        return 'rids', res

    def probe_rtree_radius(self, table_name: str, column: str, coords: List[float], radius: float):
        idx = self._indexes.get(table_name, {}).get(column)
        if not isinstance(idx, RTreeIndex):
            return None, None
        rids = idx.radius_search(tuple(coords), float(radius))
        return 'rids', rids

    # -------- Helpers --------
    @staticmethod
    def _parse_coords(val: Any):
        if isinstance(val, (list, tuple)):
            try:
                return tuple(float(x) for x in val)
            except Exception:
                return None
        if isinstance(val, str):
            s = val.strip()
            if s.startswith("[") and s.endswith("]"):
                s = s[1:-1]
            parts = [p.strip() for p in s.split(",") if p.strip() != ""]
            try:
                return tuple(float(p) for p in parts)
            except Exception:
                return None
        return None