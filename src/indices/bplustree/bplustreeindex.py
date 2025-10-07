# src/indices/bplustree/bplustreeindex.py

import os
from typing import List, Any
from ..base_index import BaseIndex
from .bplustree import BPlusTree

class BPlusTreeIndex(BaseIndex):
    def __init__(self, table_name: str, column_name: str, data_dir: str = 'data', order: int = 3):
        if order < 3:
            raise ValueError("Order must be at least 3")
            
        index_filename = f"{table_name}_{column_name}.bpt"
        self.file_path = os.path.join(data_dir, index_filename)
        
        os.makedirs(data_dir, exist_ok=True)
        
        self.tree = BPlusTree.load(self.file_path, order)
        self.tree.order = order
        self.tree.file_path = self.file_path
        self._dirty = False

    def add(self, key: Any, rid: int):
        self.tree.insert(key, rid)
        self._dirty = True
        #self.tree.save()

    def search(self, key: Any) -> List[int]:
        return self.tree.search(key)

    def remove(self, key: Any, rid: int = None):
        self.tree.remove(key, rid)
        self._dirty = True
        #self.tree.save()
        
    def rangeSearch(self, start_key: Any, end_key: Any) -> List[int]:
        return self.tree.range_search(start_key, end_key)
    
    def persist(self):
        if getattr(self, "_dirty", False):
            self.tree.save()
            self._dirty = False