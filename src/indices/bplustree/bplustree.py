# src/indices/bplustree/bplustree.py

import pickle
import bisect
import os
from typing import List

# --- Clases BPlusTreeNode, LeafNode, InternalNode (Sin Cambios) ---
# (Tu código original para estas clases va aquí)
class BPlusTreeNode:
    def __init__(self, order: int, is_leaf: bool = False):
        self.order = order
        self.is_leaf = is_leaf
        self.keys = []
        self.parent: int = -1
        self.self_offset: int = -1

    def is_full(self) -> bool:
        return len(self.keys) >= self.order - 1

class LeafNode(BPlusTreeNode):
    def __init__(self, order: int):
        super().__init__(order, is_leaf=True)
        self.values = []
        self.next_leaf: int = -1

    def add(self, key, value):
        i = bisect.bisect_left(self.keys, key)
        
        if i < len(self.keys) and self.keys[i] == key:
            self.values[i].append(value)
        else:
            self.keys.insert(i, key)
            self.values.insert(i, [value])

class InternalNode(BPlusTreeNode):
    def __init__(self, order: int):
        super().__init__(order, is_leaf=False)
        self.children: List[int] = []

    def find_child_offset(self, key) -> int:
        i = bisect.bisect_right(self.keys, key)
        return self.children[i]
# --- Fin Clases de Nodos ---

class BPlusTree:
    BLOCK_SIZE = 4096

    def __init__(self, file_path_prefix: str, order: int = 3):
        if order < 3:
            raise ValueError("Order must be at least 3")
            
        self.meta_path = f"{file_path_prefix}.meta"
        self.dat_path = f"{file_path_prefix}.dat"
        self.order = order
        self.root_offset: int = -1
        self.next_available_offset: int = 0
        self.read_count = 0
        self.write_count = 0

    # --- Métodos de I/O, Meta, Load, Initialize (Sin Cambios) ---
    # (Tu código original para _read_node, _write_node, _get_new_offset, 
    #  save_meta, _load_meta, _initialize_new_tree, load va aquí)
    def _read_node(self, offset: int) -> BPlusTreeNode:
        self.read_count += 1
        with open(self.dat_path, 'rb') as f:
            f.seek(offset)
            padded_data = f.read(self.BLOCK_SIZE)
        
        data = padded_data.rstrip(b'\0')
        if not data:
            raise IOError(f"No se pudo leer el nodo en el offset {offset}")
        
        return pickle.loads(data)

    def _write_node(self, node: BPlusTreeNode):
        self.write_count += 1
        if node.self_offset == -1:
            raise ValueError("No se puede escribir un nodo sin un 'self_offset' asignado.")
            
        data = pickle.dumps(node)
        if len(data) > self.BLOCK_SIZE:
            raise ValueError("El nodo es demasiado grande para el BLOCK_SIZE.")
        
        padded_data = data.ljust(self.BLOCK_SIZE, b'\0')
        
        with open(self.dat_path, 'r+b') as f:
            f.seek(node.self_offset)
            f.write(padded_data)

    def _get_new_offset(self) -> int:
        offset = self.next_available_offset
        self.next_available_offset += self.BLOCK_SIZE
        return offset

    def save_meta(self):
        self.write_count += 1
        metadata = {
            'root_offset': self.root_offset,
            'order': self.order,
            'next_available_offset': self.next_available_offset
        }
        with open(self.meta_path, 'wb') as f:
            pickle.dump(metadata, f)

    def _load_meta(self):
        # NOTA: La lectura del meta NO se cuenta como I/O del índice
        # porque ocurre solo una vez al cargar.
        with open(self.meta_path, 'rb') as f:
            metadata = pickle.load(f)
        self.root_offset = metadata['root_offset']
        self.order = metadata['order']
        self.next_available_offset = metadata['next_available_offset']

    def _initialize_new_tree(self):
        open(self.dat_path, 'wb').close()
        
        root = LeafNode(self.order)
        root.self_offset = self._get_new_offset()
        self.root_offset = root.self_offset
        
        self._write_node(root) # 1 escritura
        self.save_meta()       # 1 escritura (meta)

    @staticmethod
    def load(file_path_prefix: str, order: int):
        tree = BPlusTree(file_path_prefix, order)
        meta_path = f"{file_path_prefix}.meta"
        
        if os.path.exists(meta_path):
            try:
                tree._load_meta()
            except (EOFError, pickle.UnpicklingError):
                tree._initialize_new_tree()
        else:
            tree._initialize_new_tree()
            
        return tree
    # --- Fin Métodos de I/O, Meta, Load, Initialize ---

    def _find_leaf(self, key) -> LeafNode:
        # (Sin cambios)
        node_offset = self.root_offset
        node = self._read_node(node_offset) # 1+ lecturas
        
        while not node.is_leaf:
            node_offset = node.find_child_offset(key)
            node = self._read_node(node_offset) # N lecturas
            
        return node

    def insert(self, key, value):
        # (Sin cambios)
        leaf_node = self._find_leaf(key) # h lecturas
        leaf_node.add(key, value)
        
        if leaf_node.is_full():
            self._split_leaf(leaf_node) # I/O dentro de split
        else:
            self._write_node(leaf_node) # 1 escritura

    def _split_leaf(self, leaf: LeafNode):
        # (Sin cambios hasta la llamada a _insert_in_parent)
        mid = len(leaf.keys) // 2
        
        new_leaf = LeafNode(self.order)
        new_leaf.self_offset = self._get_new_offset()
        new_leaf.parent = leaf.parent # Offset del padre original
        
        new_leaf.keys = leaf.keys[mid:]
        new_leaf.values = leaf.values[mid:]
        
        new_leaf.next_leaf = leaf.next_leaf
        leaf.next_leaf = new_leaf.self_offset

        leaf.keys = leaf.keys[:mid]
        leaf.values = leaf.values[:mid]
        
        self._write_node(leaf)     # 1 escritura (hoja original actualizada)
        self._write_node(new_leaf) # 1 escritura (nueva hoja)
        
        promoted_key = new_leaf.keys[0]
        self._insert_in_parent(leaf.parent, promoted_key, leaf.self_offset, new_leaf.self_offset)

    def _insert_in_parent(self, parent_offset: int, key, left_child_offset: int, right_child_offset: int):
        
        if parent_offset == -1: # Necesitamos crear una nueva raíz
            new_root = InternalNode(self.order)
            new_root.self_offset = self._get_new_offset()
            new_root.keys = [key]
            new_root.children = [left_child_offset, right_child_offset]
            
            self.root_offset = new_root.self_offset
            
            # --- OPTIMIZACIÓN: INICIO ---
            # No necesitamos leer/escribir los hijos solo para actualizar 'parent'.
            # Los punteros 'parent' no se usan en search/insert/rangeSearch.
            # Código eliminado:
            # left_child = self._read_node(left_child_offset)   # -1 lectura
            # right_child = self._read_node(right_child_offset) # -1 lectura
            # left_child.parent = new_root.self_offset
            # right_child.parent = new_root.self_offset
            # self._write_node(left_child)                    # -1 escritura
            # self._write_node(right_child)                   # -1 escritura
            # --- OPTIMIZACIÓN: FIN ---
            
            self._write_node(new_root) # 1 escritura (nueva raíz)
            self.save_meta()           # 1 escritura (meta - root_offset cambió)
            return

        # El padre existe, leerlo
        parent_node = self._read_node(parent_offset) # 1 lectura
        
        # Insertar clave y puntero al hijo derecho en el padre (en memoria)
        i = bisect.bisect_right(parent_node.keys, key)
        parent_node.keys.insert(i, key)
        parent_node.children.insert(i + 1, right_child_offset)
        
        # --- OPTIMIZACIÓN: INICIO ---
        # No necesitamos leer/escribir el hijo derecho solo para actualizar 'parent'.
        # Código eliminado:
        # right_child = self._read_node(right_child_offset) # -1 lectura
        # right_child.parent = parent_offset
        # self._write_node(right_child)                   # -1 escritura
        # --- OPTIMIZACIÓN: FIN ---
        
        # Comprobar si el padre ahora necesita dividirse
        if parent_node.is_full():
            self._split_internal_node(parent_node) # I/O dentro de split
        else:
            self._write_node(parent_node) # 1 escritura (padre actualizado)

    def _split_internal_node(self, node: InternalNode):
        mid = len(node.keys) // 2
        promoted_key = node.keys[mid]

        # Crear nuevo nodo interno (en memoria)
        new_node = InternalNode(self.order)
        new_node.self_offset = self._get_new_offset()
        new_node.parent = node.parent # Hereda offset del padre original

        # Mover claves/hijos
        new_node.keys = node.keys[mid+1:]
        new_node.children = node.children[mid+1:]
        
        # Truncar nodo original
        node.keys = node.keys[:mid]
        node.children = node.children[:mid+1]
        
        # --- OPTIMIZACIÓN: INICIO ---
        # No necesitamos leer/escribir los hijos movidos solo para actualizar 'parent'.
        # Código eliminado:
        # for child_offset in new_node.children:
        #     child = self._read_node(child_offset) # -N lecturas
        #     child.parent = new_node.self_offset
        #     self._write_node(child)               # -N escrituras
        # --- OPTIMIZACIÓN: FIN ---

        # Escribir ambos nodos actualizados
        self._write_node(node)     # 1 escritura (nodo original actualizado)
        self._write_node(new_node) # 1 escritura (nuevo nodo interno)
        
        # Insertar la clave promocionada en el padre (recursivo)
        self._insert_in_parent(node.parent, promoted_key, node.self_offset, new_node.self_offset)

    # --- Métodos search, range_search, remove (Sin Cambios) ---
    # (Tu código original para estos métodos va aquí)
    def search(self, key) -> list:
        leaf = self._find_leaf(key) # h lecturas
        try:
            i = leaf.keys.index(key)
            return leaf.values[i]
        except ValueError:
            return []

    def range_search(self, start_key, end_key) -> list:
        results = []
        leaf_node = self._find_leaf(start_key) # h lecturas
        
        while leaf_node:
            for i, key in enumerate(leaf_node.keys):
                if start_key <= key <= end_key:
                    results.extend(leaf_node.values[i])
                elif key > end_key:
                    return results
            
            if leaf_node.next_leaf != -1:
                leaf_node = self._read_node(leaf_node.next_leaf) # 1 lectura por hoja en rango
            else:
                leaf_node = None
                
        return results

    def remove(self, key, value=None):
        leaf = self._find_leaf(key) # h lecturas
        
        original_key_count = len(leaf.keys)
        try:
            i = leaf.keys.index(key)
            modified = False
            if value: # Eliminar RID específico
                if value in leaf.values[i]:
                    leaf.values[i].remove(value)
                    if not leaf.values[i]: # Si la lista de RIDs queda vacía
                        leaf.keys.pop(i)
                        leaf.values.pop(i)
                    modified = True
                else:
                    return # RID no encontrado
            else: # Eliminar clave completa
                leaf.keys.pop(i)
                leaf.values.pop(i)
                modified = True
            
            if modified:
                 self._write_node(leaf) # 1 escritura si se modificó

        except (ValueError, IndexError):
            pass # Clave no encontrada