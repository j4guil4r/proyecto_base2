# src/core/record.py

import struct
from typing import List, Any, Tuple

class RecordManager:
    def __init__(self, schema: List[Tuple[str, str, int]]):
        self.schema = schema
        self.array_dimensions = {} 
        self.format_string = self._build_format_string()
        self.record_size = struct.calcsize(self.format_string)
        print(f"RecordManager creado. Schema: {self.schema}, Formato: '{self.format_string}', Tamaño: {self.record_size} bytes") # Debug print

    def _build_format_string(self) -> str:
        format_parts = []
        for col_name, col_type, length in self.schema: 
            col_type_upper = col_type.upper()
            if col_type_upper == 'INT':
                format_parts.append('i') 
            elif col_type_upper == 'FLOAT':
                format_parts.append('d') 
            elif col_type_upper == 'VARCHAR':
                format_parts.append(f'{length}s') 
            elif col_type_upper == 'ARRAY[FLOAT]':
                num_floats = length // 8
                if num_floats <= 0:
                     raise ValueError(f"Longitud inválida ({length}) para ARRAY[FLOAT] '{col_name}'. Debe ser múltiplo de 8.")
                format_parts.append('d' * num_floats) 
                self.array_dimensions[col_name] = num_floats 
            else:
                 print(f"Advertencia: Tipo desconocido '{col_type}' en schema. Ignorado en format string.")

        return '<' + ''.join(format_parts)

    def pack(self, values: List[Any]) -> bytes:
        packed_values = []
        if len(values) != len(self.schema):
             raise ValueError(f"Se esperaban {len(self.schema)} valores, pero se recibieron {len(values)}")

        for i, value in enumerate(values):
            col_name, col_type, length = self.schema[i]
            col_type_upper = col_type.upper()

            if col_type_upper == 'VARCHAR':
                encoded_value = str(value).encode('utf-8')
                packed_values.append(encoded_value.ljust(length, b'\0'))
            elif col_type_upper == 'ARRAY[FLOAT]':
                if not isinstance(value, (tuple, list)):
                     raise TypeError(f"Se esperaba una tupla/lista para ARRAY[FLOAT] '{col_name}', se recibió {type(value)}")
                num_expected = self.array_dimensions.get(col_name)
                if num_expected is None: # No debería pasar si _build_format_string funcionó
                     raise RuntimeError(f"Dimensiones no encontradas para ARRAY[FLOAT] '{col_name}'")
                if len(value) != num_expected:
                     raise ValueError(f"Se esperaban {num_expected} floats para ARRAY[FLOAT] '{col_name}', se recibieron {len(value)}")
                # Extender la lista con los floats individuales de la tupla/lista
                packed_values.extend(float(v) for v in value)
            else: 
                packed_values.append(value)

        try:
            return struct.pack(self.format_string, *packed_values)
        except struct.error as e:
            print(f"Error al empaquetar con struct: {e}")
            print(f"  - Formato Esperado: {self.format_string}")
            print(f"  - Valores Pasados ({len(packed_values)}): {packed_values}")
            # Intentar dar más detalles sobre el valor problemático
            expected_count = len(self.format_string) -1 # Quitar el '<'
            # (Contar 'd's múltiples como varios items)
            # ... (código más complejo para contar items en format_string)
            raise

    def unpack(self, data: bytes) -> Tuple[Any, ...]:
        if len(data) != self.record_size:
             raise ValueError(f"Tamaño de datos incorrecto. Se esperaban {self.record_size} bytes, se recibieron {len(data)}.")

        try:
            # Desempacar todos los valores base
            unpacked_flat_values = list(struct.unpack(self.format_string, data))
        except struct.error as e:
            print(f"Error al desempacar con struct: {e}")
            print(f"  - Formato Esperado: {self.format_string}")
            print(f"  - Tamaño de Datos: {len(data)}")
            raise

        result_values = []
        current_flat_index = 0
        for col_name, col_type, length in self.schema:
            col_type_upper = col_type.upper()

            if col_type_upper == 'VARCHAR':
                # Tomar el valor de bytes y decodificar/limpiar
                value_bytes = unpacked_flat_values[current_flat_index]
                result_values.append(value_bytes.strip(b'\0').decode('utf-8', errors='replace'))
                current_flat_index += 1
            # --- CORRECCIÓN: Manejar ARRAY[FLOAT] ---
            elif col_type_upper == 'ARRAY[FLOAT]':
                num_floats = self.array_dimensions.get(col_name)
                if num_floats is None:
                    # Omitir si no se pudo determinar dimensiones
                    print(f"Advertencia: Omitiendo ARRAY[FLOAT] '{col_name}' al desempacar (dimensiones desconocidas).")
                    continue # Saltar esta columna

                # Tomar los próximos 'num_floats' valores de la lista plana
                array_values = unpacked_flat_values[current_flat_index : current_flat_index + num_floats]
                result_values.append(tuple(array_values)) # Guardar como tupla
                current_flat_index += num_floats
            # --- FIN CORRECCIÓN ---
            elif col_type_upper in ('INT', 'FLOAT'):
                 # Tomar el valor numérico directamente
                 result_values.append(unpacked_flat_values[current_flat_index])
                 current_flat_index += 1
            else:
                 # Si hay tipos desconocidos, podríamos necesitar saltar bytes o manejarlo
                 # Por ahora, asumimos que no hay y avanzamos si _build los ignoró.
                 # Si _build los incluyó erróneamente, esto fallará.
                 print(f"Advertencia: Tipo '{col_type}' desconocido encontrado al desempacar '{col_name}'.")
                 # Intentar avanzar si solo hay un item (no siempre correcto)
                 if current_flat_index < len(unpacked_flat_values):
                      result_values.append(unpacked_flat_values[current_flat_index]) # Añadir como venga
                      current_flat_index += 1
                 else:
                      result_values.append(None) # O añadir None si no hay más datos

        # Comprobación final
        if len(result_values) != len(self.schema):
             print(f"Advertencia: Discrepancia en conteo de columnas al desempacar. Schema: {len(self.schema)}, Resultado: {len(result_values)}")

        return tuple(result_values)