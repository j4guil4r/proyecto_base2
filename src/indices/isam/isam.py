# src/indices/isam/isam.py

import pickle
import math
import os  
from typing import List, Any, Tuple

class IndexNode:
    def __init__(self, capacity: int):
        self.keys: List[Any] = []
        self.pointers: List[int] = []
        self.capacity = capacity

    def is_full(self) -> bool:
        return len(self.keys) >= self.capacity

class DataPage:
    def __init__(self, capacity: int):
        self.records: List[Tuple[Any, int, bool]] = []
        self.capacity = capacity
        self.next_overflow_offset = -1

    def is_full(self) -> bool:
        return len(self.records) >= self.capacity

class ISAM:
    BLOCK_SIZE = 4096

    def __init__(self, file_path_prefix: str, index_capacity=4, data_capacity=4):
        self.prefix = file_path_prefix
        self.paths = {
            'meta': f"{self.prefix}.meta",
            'idx2': f"{self.prefix}.idx2",
            'idx1': f"{self.prefix}.idx1",
            'dat': f"{self.prefix}.dat",
            'ovf': f"{self.prefix}.ovf"
        }
        self.index_capacity = index_capacity
        self.data_capacity = data_capacity
        self.root_offset_l2 = 0
        self.data_page_offsets: List[int] = []
        self.read_count = 0
        self.write_count = 0

    def _write_block(self, file_key: str, block: Any, offset: int = None) -> int:
        self.write_count += 1
        data = pickle.dumps(block)
        
        if len(data) > self.BLOCK_SIZE:
            raise ValueError(f"Error: El bloque ({type(block)}) es demasiado grande ({len(data)} bytes) para el BLOCK_SIZE ({self.BLOCK_SIZE}).")
        
        padded_data = data.ljust(self.BLOCK_SIZE, b'\0')
        
        with open(self.paths[file_key], 'r+b' if os.path.exists(self.paths[file_key]) else 'w+b') as f:
            if offset is not None:
                f.seek(offset)
            else:
                f.seek(0, 2)
            
            pos = f.tell()
            f.write(padded_data)
            return pos

    def _read_block(self, file_key: str, offset: int) -> Any:
        self.read_count += 1
        with open(self.paths[file_key], 'rb') as f:
            f.seek(offset)
            padded_data = f.read(self.BLOCK_SIZE)
            if not padded_data:
                raise EOFError(f"Error al leer bloque en offset {offset} de {self.paths[file_key]}")
                
            data = padded_data.rstrip(b'\0')
            
            try:
                return pickle.loads(data)
            except pickle.UnpicklingError as e:
                print(f"Error de Pickle en {self.paths[file_key]} offset {offset}.")
                raise e

    def build(self, sorted_records: List[Tuple[Any, int]]):
        if not sorted_records:
            return

        self.data_page_offsets = []
        
        for key in ['idx2', 'idx1', 'dat', 'ovf']:
            if os.path.exists(self.paths[key]):
                open(self.paths[key], 'wb').close()

        data_pages = []
        current_page = DataPage(self.data_capacity)
        for key, rid in sorted_records:
            if current_page.is_full():
                data_pages.append(current_page)
                current_page = DataPage(self.data_capacity)
            
            current_page.records.append((key, rid, True))
            
        if current_page.records:
            data_pages.append(current_page)

        index1_entries = []
        for page in data_pages:
            offset = self._write_block('dat', page)
            self.data_page_offsets.append(offset)
            
            highest_key = page.records[-1][0]
            index1_entries.append((highest_key, offset))

        index1_nodes = []
        current_node = IndexNode(self.index_capacity)
        for key, pointer in index1_entries:
            if current_node.is_full():
                index1_nodes.append(current_node)
                current_node = IndexNode(self.index_capacity)
            current_node.keys.append(key)
            current_node.pointers.append(pointer)
        if current_node.keys:
            index1_nodes.append(current_node)

        index2_entries = []
        for node in index1_nodes:
            offset = self._write_block('idx1', node)
            highest_key = node.keys[-1]
            index2_entries.append((highest_key, offset))
            
        root_node = IndexNode(self.index_capacity)
        
        if len(index2_entries) <= self.index_capacity:
             for key, pointer in index2_entries:
                root_node.keys.append(key)
                root_node.pointers.append(pointer)
             self.root_offset_l2 = self._write_block('idx2', root_node, 0)
        else:
             print(f"Advertencia: ISAM Nivel 2 tiene {len(index2_entries)} entradas pero capacidad {self.index_capacity}.")
             
             for key, pointer in index2_entries:
                if root_node.is_full():
                     print(f"ERROR: Raíz L2 llena. {key} descartado.")
                     break
                root_node.keys.append(key)
                root_node.pointers.append(pointer)
             self.root_offset_l2 = self._write_block('idx2', root_node, 0)

        self.save_metadata()

    def search(self, key: Any) -> List[int]:
        root = self._read_block('idx2', self.root_offset_l2)
        
        l1_offset = self._find_pointer(root, key)
        if l1_offset is None: return []
        
        l1_node = self._read_block('idx1', l1_offset)
        data_page_offset = self._find_pointer(l1_node, key)
        if data_page_offset is None: return []

        results = []
        current_page_offset = data_page_offset
        current_page_file = 'dat'
        
        while current_page_offset != -1:
            current_page = self._read_block(current_page_file, current_page_offset)
            
            for k, rid, is_active in current_page.records:
                if k == key and is_active:
                    results.append(rid)
            
            current_page_offset = current_page.next_overflow_offset
            current_page_file = 'ovf' 
            
        return results

    def _find_pointer(self, node: IndexNode, key: Any) -> int:
        for i, k in enumerate(node.keys):
            if key <= k:
                return node.pointers[i]
        if node.pointers:
            return node.pointers[-1]
        return None

    def add(self, key: Any, rid: int):
        root = self._read_block('idx2', self.root_offset_l2)
        l1_offset = self._find_pointer(root, key)
        if l1_offset is None: raise IndexError("No se pudo encontrar un puntero L1 para la clave.")
        
        l1_node = self._read_block('idx1', l1_offset)
        data_page_offset = self._find_pointer(l1_node, key)
        if data_page_offset is None: raise IndexError("No se pudo encontrar un puntero de página de datos para la clave.")
        
        current_page_offset = data_page_offset
        current_page_file = 'dat'
        page = self._read_block(current_page_file, current_page_offset)

        last_page_info = {'file': current_page_file, 'offset': current_page_offset, 'page': page}
        while last_page_info['page'].next_overflow_offset != -1:
            last_page_info['offset'] = last_page_info['page'].next_overflow_offset
            last_page_info['file'] = 'ovf'
            last_page_info['page'] = self._read_block(last_page_info['file'], last_page_info['offset'])
        
        page_to_modify = last_page_info['page']
        if not page_to_modify.is_full():
            page_to_modify.records.append((key, rid, True))
            page_to_modify.records.sort(key=lambda x: x[0])
            self._write_block(last_page_info['file'], page_to_modify, last_page_info['offset'])
        else:
            new_ovf_page = DataPage(self.data_capacity)
            new_ovf_page.records.append((key, rid, True))
            
            new_offset = self._write_block('ovf', new_ovf_page, offset=None)
            
            page_to_modify.next_overflow_offset = new_offset
            self._write_block(last_page_info['file'], page_to_modify, last_page_info['offset'])

    def save_metadata(self):
        meta = {
            'root_offset_l2': self.root_offset_l2,
            'index_capacity': self.index_capacity,
            'data_capacity': self.data_capacity,
            'data_page_offsets': self.data_page_offsets 
        }
        with open(self.paths['meta'], 'wb') as f:
            pickle.dump(meta, f)

    def load_metadata(self):
        with open(self.paths['meta'], 'rb') as f:
            meta = pickle.load(f)
        self.root_offset_l2 = meta['root_offset_l2']
        self.index_capacity = meta['index_capacity']
        self.data_capacity = meta['data_capacity']
        self.data_page_offsets = meta.get('data_page_offsets', [])

    def remove(self, key: Any):
        root = self._read_block('idx2', self.root_offset_l2)
        l1_offset = self._find_pointer(root, key)
        if l1_offset is None: return 

        l1_node = self._read_block('idx1', l1_offset)
        data_page_offset = self._find_pointer(l1_node, key)
        if data_page_offset is None: return 

        current_page_offset = data_page_offset
        current_page_file = 'dat'
        
        while current_page_offset != -1:
            page = self._read_block(current_page_file, current_page_offset)
            modified = False
            
            for i, (k, rid, is_active) in enumerate(page.records):
                if k == key and is_active:
                    page.records[i] = (k, rid, False)
                    modified = True
            
            if modified:
                self._write_block(current_page_file, page, current_page_offset)
            
            if page.records and page.records[-1][0] < key:
                 break
            
            current_page_offset = page.next_overflow_offset
            current_page_file = 'ovf'

    def rangeSearch(self, start_key: Any, end_key: Any) -> List[int]:
        results = []
        root = self._read_block('idx2', self.root_offset_l2)
        l1_offset = self._find_pointer(root, start_key)
        if l1_offset is None: return []
        
        l1_node = self._read_block('idx1', l1_offset)
        start_page_offset = self._find_pointer(l1_node, start_key)
        if start_page_offset is None: return []

        try:
            start_idx = self.data_page_offsets.index(start_page_offset)
        except ValueError:
            return [] 

        stop_main_scan = False
        for i in range(start_idx, len(self.data_page_offsets)):
            if stop_main_scan:
                break 

            current_page_offset = self.data_page_offsets[i]
            current_page_file = 'dat'
            
            while current_page_offset != -1:
                page = self._read_block(current_page_file, current_page_offset)
                
                for k, rid, is_active in page.records:
                    if not is_active:
                        continue
                    
                    if k >= start_key and k <= end_key:
                        results.append(rid)
                    
                    if k > end_key:
                        if current_page_file == 'dat':
                            stop_main_scan = True
                            break
                        else:
                            current_page_offset = -1 
                            break 
                
                if current_page_offset != -1:
                    current_page_offset = page.next_overflow_offset
                    current_page_file = 'ovf'
        
        return results