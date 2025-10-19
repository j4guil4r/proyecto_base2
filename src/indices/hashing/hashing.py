# src/indices/hashing/hashing.py

import pickle
import os
from typing import List, Tuple, Any

class Bucket:
    def __init__(self, depth: int, size: int):
        self.local_depth = depth
        self.size = size
        self.values: List[Tuple[Any, int]] = []

    def is_full(self) -> bool:
        return len(self.values) >= self.size

    def add(self, key: Any, rid: int):
        if not self.is_full():
            self.values.append((key, rid))
            return True
        return False

    def get_records(self, key: Any) -> List[int]:
        return [r for k, r in self.values if k == key]

class Directory:
    BLOCK_SIZE = 4096

    def __init__(self, file_path_prefix: str, bucket_size: int = 4):
        self.meta_path = f"{file_path_prefix}.meta"
        self.dat_path = f"{file_path_prefix}.dat"
        
        self.bucket_size = bucket_size
        self.global_depth = 1
        self.bucket_pointers: List[int] = []
        self.read_count = 0
        self.write_count = 0

    def _hash(self, key: Any) -> int:
        return hash(key)

    def _get_bucket_index(self, key: Any) -> int:
        h = self._hash(key)
        return h & ((1 << self.global_depth) - 1)

    def _read_bucket(self, offset: int) -> Bucket:
        self.read_count += 1
        with open(self.dat_path, 'rb') as f:
            f.seek(offset)
            padded_data = f.read(self.BLOCK_SIZE)
            if not padded_data:
                raise EOFError(f"Se intentó leer un bucket en un offset ({offset}) que estaba vacío o corrupto.")
            
            data = padded_data.rstrip(b'\0')
            
            try:
                return pickle.loads(data)
            except pickle.UnpicklingError as e:
                print(f"Error al deserializar bucket en offset {offset}. Datos (primeros 100 bytes): {data[:100]}")
                raise e

    def _write_bucket(self, bucket: Bucket, offset: int = None) -> int:
        self.write_count += 1
        data = pickle.dumps(bucket)
        
        if len(data) > self.BLOCK_SIZE:
            raise ValueError(f"Error: El bucket (bucket_size={self.bucket_size}) es demasiado grande ({len(data)} bytes) para el tamaño de bloque ({self.BLOCK_SIZE} bytes). Considere aumentar BLOCK_SIZE o disminuir bucket_size.")
        
        padded_data = data.ljust(self.BLOCK_SIZE, b'\0')
        
        with open(self.dat_path, 'r+b' if os.path.exists(self.dat_path) else 'w+b') as f:
            if offset is not None:
                f.seek(offset)
            else:
                f.seek(0, 2)
            
            pos = f.tell()
            f.write(padded_data)
            return pos

    def initialize(self):
        open(self.dat_path, 'wb').close()
        
        b1 = Bucket(1, self.bucket_size)
        b2 = Bucket(1, self.bucket_size)
        
        offset1 = self._write_bucket(b1, offset=None)
        offset2 = self._write_bucket(b2, offset=None)
        
        self.bucket_pointers = [offset1, offset2]
        self.save()

    def search(self, key: Any) -> List[int]:
        bucket_index = self._get_bucket_index(key)
        bucket_offset = self.bucket_pointers[bucket_index]
        bucket = self._read_bucket(bucket_offset)
        return bucket.get_records(key)

    def add(self, key: Any, rid: int):
        bucket_index = self._get_bucket_index(key)
        bucket_offset = self.bucket_pointers[bucket_index]
        bucket = self._read_bucket(bucket_offset)

        if bucket.add(key, rid):
            self._write_bucket(bucket, bucket_offset)
            return

        self._split_bucket(bucket_index, bucket, bucket_offset)
        self.add(key, rid)

    def _split_bucket(self, bucket_index: int, old_bucket: Bucket, old_bucket_offset: int):
        old_bucket.local_depth += 1
        
        if old_bucket.local_depth > self.global_depth:
            self._grow_directory()

        new_bucket = Bucket(old_bucket.local_depth, self.bucket_size)
        new_bucket_offset = self._write_bucket(new_bucket, offset=None)
        
        current_values = old_bucket.values
        old_bucket.values = []
        
        split_index_pattern = 1 << (old_bucket.local_depth - 1)
        
        for i in range(len(self.bucket_pointers)):
            if self.bucket_pointers[i] == old_bucket_offset and (i & split_index_pattern):
                self.bucket_pointers[i] = new_bucket_offset

        temp_buckets = {
            old_bucket_offset: old_bucket,
            new_bucket_offset: new_bucket
        }
        
        for k, r in current_values:
            idx = self._get_bucket_index(k)
            offset = self.bucket_pointers[idx]
            temp_buckets[offset].add(k, r)

        self._write_bucket(old_bucket, old_bucket_offset)
        self._write_bucket(new_bucket, new_bucket_offset)

    def _grow_directory(self):
        self.bucket_pointers.extend(self.bucket_pointers)
        self.global_depth += 1
        
    def save(self):
        self.write_count += 1
        metadata = {
            'global_depth': self.global_depth,
            'bucket_size': self.bucket_size,
            'bucket_pointers': self.bucket_pointers
        }
        with open(self.meta_path, 'wb') as f:
            pickle.dump(metadata, f)

    @staticmethod
    def load(file_path_prefix: str, bucket_size_if_new: int = 4):
        meta_path = f"{file_path_prefix}.meta"
        
        if os.path.exists(meta_path):
            try:
                with open(meta_path, 'rb') as f:
                    metadata = pickle.load(f)
                
                directory = Directory(file_path_prefix, metadata['bucket_size'])
                directory.global_depth = metadata['global_depth']
                directory.bucket_pointers = metadata['bucket_pointers']
                return directory
            except (EOFError, pickle.UnpicklingError):
                pass
        
        directory = Directory(file_path_prefix, bucket_size_if_new)
        directory.initialize()
        return directory