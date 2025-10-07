# src/indices/sequentialfile/sequentialfileindex.py

import os
from typing import List, Any
from ..base_index import BaseIndex
from .sequentialfile import SequentialFile

class SequentialFileIndex(BaseIndex):
    def __init__(self, table_name: str, column_name: str,
                 record_manager, key_column_index: int,
                 data_dir: str = 'data', aux_capacity: int = 10):
        
        file_prefix = os.path.join(data_dir, f"{table_name}_{column_name}_seq")
        
        os.makedirs(data_dir, exist_ok=True)

        self.engine = SequentialFile(
            file_path_prefix=file_prefix,
            record_manager=record_manager,
            key_column_index=key_column_index,
            aux_capacity=aux_capacity
        )

    def add(self, key: Any, rid_or_values):
        if not isinstance(rid_or_values, list):
            raise TypeError("SequentialFileIndex.add espera una lista de valores de registro.")
        self.engine.add(rid_or_values)

    def search(self, key: Any) -> List[Any]:
        return self.engine.search(key)

    def remove(self, key: Any, rid: int = None):
        print(f"WARN: La operación de borrado en Archivo Secuencial es costosa e implica una reconstrucción.")
        
        main_records = list(self.engine._read_records_from_file(self.engine.main_path))
        aux_records = list(self.engine._read_records_from_file(self.engine.aux_path))
        
        kept_records = [r for r in (main_records + aux_records) if r[self.engine.key_col_idx] != key]
        
        kept_records.sort(key=lambda r: r[self.engine.key_col_idx])
        
        with open(self.engine.main_path, 'wb') as f:
            for record in kept_records:
                f.write(self.engine.record_manager.pack(record))

        open(self.engine.aux_path, 'w').close()

    def rangeSearch(self, start_key: Any, end_key: Any) -> List[Any]:
        return self.engine.range_search(start_key, end_key)