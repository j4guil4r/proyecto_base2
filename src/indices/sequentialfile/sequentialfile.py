# src/indices/sequentialfile/sequentialfile.py

import os
import pickle # Aunque no lo usas directamente, lo dejamos por si acaso
import bisect
import time # Para un posible reintento
from typing import List, Any, Generator, Optional, Tuple

class SequentialFile:
    def __init__(self, file_path_prefix: str, record_manager, key_column_index: int, aux_capacity: int = 10):
        self.prefix = file_path_prefix
        self.main_path = f"{self.prefix}.dat"
        self.aux_path = f"{self.prefix}.aux"
        
        self.record_manager = record_manager
        self.key_col_idx = key_column_index
        self.aux_capacity = aux_capacity
        
        self.read_count = 0
        self.write_count = 0
        
        # Asegurarse de que los archivos existan al inicio (más robusto)
        for path in [self.main_path, self.aux_path]:
            if not os.path.exists(path):
                try:
                    with open(path, 'wb') as f: # Crear vacío si no existe
                        pass
                    print(f"Archivo creado: {path}")
                except IOError as e:
                    # Error crítico si no podemos crear los archivos base
                    raise IOError(f"Error fatal creando archivo {path}: {e}")

    def _get_record_count(self, file_path: str) -> int:
        record_size = self.record_manager.record_size
        if record_size == 0: return 0
        try:
            # Usar os.path.getsize es seguro y no requiere abrir/cerrar
            if os.path.exists(file_path):
                 return os.path.getsize(file_path) // record_size
            else:
                 return 0
        except OSError as e: # Captura errores como permisos denegados
            print(f"Error obteniendo tamaño de {file_path}: {e}")
            return 0 # Asumir 0 si hay error

    def _get_aux_count(self) -> int:
        return self._get_record_count(self.aux_path)

    def _read_records_from_file(self, file_path: str) -> Generator[list, None, None]:
        record_size = self.record_manager.record_size
        try:
            # Uso correcto de 'with'
            with open(file_path, 'rb') as f:
                while True:
                    packed_data = f.read(record_size)
                    self.read_count += 1
                    if not packed_data or len(packed_data) < record_size:
                        break
                    try:
                        yield list(self.record_manager.unpack(packed_data))
                    except Exception as e: # Capturar error de unpack
                        print(f"Error desempacando registro en {file_path}: {e}")
                        # Continuar con el siguiente registro si es posible
        except FileNotFoundError:
             # Silencioso si el archivo no existe (ej. .dat vacío al inicio)
             return
        except IOError as e:
             print(f"Error leyendo {file_path}: {e}")
             return # Detener generador si hay error de I/O

    def _read_record_at_index(self, file_path: str, index: int) -> Optional[Tuple]:
        record_size = self.record_manager.record_size
        offset = index * record_size
        try:
            # Uso correcto de 'with'
            with open(file_path, 'rb') as f:
                f.seek(offset)
                packed_data = f.read(record_size)
                self.read_count += 1
                if packed_data and len(packed_data) == record_size:
                    try:
                        return self.record_manager.unpack(packed_data)
                    except Exception as e:
                        print(f"Error desempacando registro en {file_path}, offset {offset}: {e}")
                        return None # Devolver None si el registro está corrupto
        except (IOError, FileNotFoundError):
            # Errores al buscar/leer (ej. índice fuera de rango)
            pass
        return None

    def _find_first_record_gte(self, key: Any) -> int:
        low = 0
        # Llamada segura a _get_record_count
        high = self._get_record_count(self.main_path)

        while low < high:
            mid = (low + high) // 2
            record = self._read_record_at_index(self.main_path, mid)

            # Si _read_record_at_index falló (ej. I/O error), retroceder
            if record is None:
                high = mid
                continue

            try:
                record_key = record[self.key_col_idx]
                if record_key < key:
                    low = mid + 1
                else:
                    high = mid
            except IndexError:
                 # Error si el índice de columna es inválido (debería fallar antes)
                 print(f"Error: Índice de columna clave {self.key_col_idx} fuera de rango.")
                 high = mid # Tratar como error y retroceder

        return low

    def add(self, record_values: list):
        packed_record = self.record_manager.pack(record_values)
        try:
            # Uso correcto de 'with'
            with open(self.aux_path, 'ab') as f:
                f.write(packed_record)
                self.write_count += 1
        except IOError as e:
             print(f"Error crítico: No se pudo escribir en archivo auxiliar {self.aux_path}: {e}")
             # Considerar lanzar una excepción aquí si la escritura es vital
             return

        # Comprobar capacidad después de escribir
        if self._get_aux_count() >= self.aux_capacity:
            self.reconstruct()

    def reconstruct(self):
        print("-> Capacidad del archivo auxiliar alcanzada. Iniciando reconstrucción...")

        main_records = []
        aux_records = []
        all_records = []
        temp_main_path = self.main_path + '.tmp'
        max_retries = 3 # Número máximo de reintentos para os.replace
        retry_delay = 0.1 # Segundos de espera entre reintentos

        try:
            # Leer todo (los 'with' internos se encargan de cerrar)
            main_records = list(self._read_records_from_file(self.main_path))
            aux_records = list(self._read_records_from_file(self.aux_path))

            # Combinar y ordenar en memoria
            all_records = main_records + aux_records
            all_records.sort(key=lambda r: r[self.key_col_idx])

            # Escribir en el archivo temporal (se cierra al salir del 'with')
            with open(temp_main_path, 'wb') as f_temp:
                for record in all_records:
                    f_temp.write(self.record_manager.pack(record))
                    self.write_count += 1

            # --- INTENTAR REEMPLAZAR CON REINTENTOS ---
            for attempt in range(max_retries):
                try:
                    os.replace(temp_main_path, self.main_path)
                    print("   Archivo principal reemplazado.")
                    # Si tiene éxito, limpiar auxiliar y salir del bucle de reintento
                    try:
                        with open(self.aux_path, 'wb') as f_aux_clear: # Usar 'with' aquí también
                            pass
                        print("   Archivo auxiliar limpiado.")
                    except IOError as e_aux:
                         print(f"   Advertencia: No se pudo limpiar {self.aux_path}: {e_aux}")
                    break # Salir del bucle for de reintentos
                except OSError as e_replace:
                    print(f"   Intento {attempt + 1}/{max_retries}: Error reemplazando {self.main_path}: {e_replace}")
                    if attempt < max_retries - 1:
                        print(f"   Esperando {retry_delay}s antes de reintentar...")
                        time.sleep(retry_delay)
                    else:
                        # Si fallan todos los reintentos, lanzar el error
                        raise IOError(f"Fallo al reemplazar {self.main_path} después de {max_retries} intentos: {e_replace}")

            print("-> Reconstrucción completada.")

        except FileNotFoundError as e:
            print(f"Error crítico durante reconstrucción: Archivo no encontrado - {e}")
            # Considerar eliminar .tmp si existe
            if os.path.exists(temp_main_path): os.remove(temp_main_path)
        except IOError as e:
            print(f"Error crítico de I/O durante reconstrucción: {e}")
            if os.path.exists(temp_main_path): os.remove(temp_main_path)
        except Exception as e:
            print(f"Error inesperado durante reconstrucción: {e}")
            if os.path.exists(temp_main_path): os.remove(temp_main_path)

    def search(self, key: Any) -> List[list]:
       # ... (Tu código sin cambios, ya usa 'with' indirectamente) ...
        results = []
        for record in self._read_records_from_file(self.aux_path):
            if record[self.key_col_idx] == key: results.append(record)
        start_idx = self._find_first_record_gte(key)
        record_count = self._get_record_count(self.main_path)
        for i in range(start_idx, record_count):
            record = self._read_record_at_index(self.main_path, i)
            if record is None: break
            record_key = record[self.key_col_idx]
            if record_key == key: results.append(list(record))
            elif record_key > key: break
        return results

    def range_search(self, start_key: Any, end_key: Any) -> List[list]:
        # ... (Tu código sin cambios, ya usa 'with' indirectamente) ...
        results = []
        for record in self._read_records_from_file(self.aux_path):
            if start_key <= record[self.key_col_idx] <= end_key: results.append(record)
        start_idx = self._find_first_record_gte(start_key)
        record_count = self._get_record_count(self.main_path)
        for i in range(start_idx, record_count):
            record = self._read_record_at_index(self.main_path, i)
            if record is None: break
            record_key = record[self.key_col_idx]
            if record_key <= end_key: results.append(list(record))
            else: break
        results.sort(key=lambda r: r[self.key_col_idx])
        return results