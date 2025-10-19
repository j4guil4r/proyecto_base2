# run_experiments.py
import time
import shutil
import os
import random
from src.core.engine import DatabaseEngine
from src.indices.isam.isamindex import ISAMIndex

# --- 1. CONFIGURACIÓN GENERAL ---
DB_DIR = 'experimental_data'
NUM_INSERTS = 1000
NUM_SEARCHES = 200
NUM_RANGE_SEARCHES = 100
RANGE_SIZE = 20

print(f"Limpiando directorio de datos: {DB_DIR}")
shutil.rmtree(DB_DIR, ignore_errors=True)
os.makedirs(DB_DIR, exist_ok=True)

print("Inicializando Database Engine...")
engine = DatabaseEngine(data_dir=DB_DIR)

# Rango de IDs a usar en las pruebas
start_id = 1
end_id = start_id + NUM_INSERTS
inserted_ids_ordered = list(range(start_id, end_id))
inserted_ids_shuffled = inserted_ids_ordered[:]
random.shuffle(inserted_ids_shuffled)

# --- B+TREE INDEX ---
print("\n" + "="*10 + " B+TREE " + "="*10)
TABLE_NAME_BTREE = "tabla_btree"
INDEX_NAME_BTREE = "id"
SCHEMA_BTREE = f"{INDEX_NAME_BTREE} INT INDEX BTREE, data VARCHAR[50]"
try:
    print(f"Creando tabla '{TABLE_NAME_BTREE}'...")
    engine.execute(f"CREATE TABLE {TABLE_NAME_BTREE} ({SCHEMA_BTREE})")
    print(f"Tabla '{TABLE_NAME_BTREE}' creada.")
    index_obj = engine.tables[TABLE_NAME_BTREE].indexes[INDEX_NAME_BTREE]
    btree_engine_obj = index_obj.tree

    # --- INSERCIÓN (B+Tree) ---
    print(f"\n--- Prueba INSERCIÓN (B+Tree) ---")
    btree_engine_obj.read_count = 0; btree_engine_obj.write_count = 0
    start_time = time.perf_counter()
    print(f"Realizando {NUM_INSERTS} inserciones (orden aleatorio)...")
    for i, record_id in enumerate(inserted_ids_shuffled):
        engine.execute(f"INSERT INTO {TABLE_NAME_BTREE} VALUES ({record_id}, 'Dato_{i}')")
    end_time = time.perf_counter()
    btree_engine_obj.save_meta()
    duration_ms = (end_time - start_time) * 1000
    reads = btree_engine_obj.read_count; writes = btree_engine_obj.write_count
    print(f"T: {duration_ms:.2f} ms | Prom: {(duration_ms / NUM_INSERTS):.4f} ms/ins | R: {reads} | W: {writes}")

    # --- BÚSQUEDA ESPECÍFICA (B+Tree) ---
    print(f"\n--- Prueba BÚSQUEDA ESPECÍFICA (B+Tree) ---")
    keys_to_search = random.sample(inserted_ids_ordered, min(NUM_SEARCHES, len(inserted_ids_ordered)))
    btree_engine_obj.read_count = 0; btree_engine_obj.write_count = 0
    search_times = []
    print(f"Realizando {len(keys_to_search)} búsquedas...")
    for key in keys_to_search:
        op_start = time.perf_counter()
        results = engine.execute(f"SELECT * FROM {TABLE_NAME_BTREE} WHERE {INDEX_NAME_BTREE} = {key}")
        op_end = time.perf_counter()
        search_times.append((op_end - op_start) * 1000)
    total_duration_ms = sum(search_times)
    reads = btree_engine_obj.read_count; writes = btree_engine_obj.write_count
    print(f"T: {total_duration_ms:.2f} ms | Prom: {(total_duration_ms / len(keys_to_search)):.4f} ms/bús | R: {reads} (Prom: {reads / len(keys_to_search):.2f}) | W: {writes}")

    # --- BÚSQUEDA POR RANGO (B+Tree) ---
    print(f"\n--- Prueba BÚSQUEDA POR RANGO (B+Tree) ---")
    btree_engine_obj.read_count = 0; btree_engine_obj.write_count = 0
    range_search_times = []
    print(f"Realizando {NUM_RANGE_SEARCHES} búsquedas (tamaño {RANGE_SIZE})...")
    for _ in range(NUM_RANGE_SEARCHES):
        start_range_key = random.randint(start_id, end_id - RANGE_SIZE - 1)
        end_range_key = start_range_key + RANGE_SIZE
        op_start = time.perf_counter()
        results = engine.execute(f"SELECT * FROM {TABLE_NAME_BTREE} WHERE {INDEX_NAME_BTREE} BETWEEN {start_range_key} AND {end_range_key}")
        op_end = time.perf_counter()
        range_search_times.append((op_end - op_start) * 1000)
    total_duration_ms = sum(range_search_times)
    reads = btree_engine_obj.read_count; writes = btree_engine_obj.write_count
    print(f"T: {total_duration_ms:.2f} ms | Prom: {(total_duration_ms / NUM_RANGE_SEARCHES):.4f} ms/bús | R: {reads} (Prom: {reads / NUM_RANGE_SEARCHES:.2f}) | W: {writes}")

except Exception as e: print(f"Error B+Tree: {e}")
print("="*30)

# --- HASH INDEX ---
print("\n" + "="*10 + " HASH INDEX " + "="*10)
TABLE_NAME_HASH = "tabla_hash"
INDEX_NAME_HASH = "id"
SCHEMA_HASH = f"{INDEX_NAME_HASH} INT INDEX HASH, data VARCHAR[50]"
try:
    print(f"Creando tabla '{TABLE_NAME_HASH}'...")
    engine.execute(f"CREATE TABLE {TABLE_NAME_HASH} ({SCHEMA_HASH})")
    print(f"Tabla '{TABLE_NAME_HASH}' creada.")
    index_obj = engine.tables[TABLE_NAME_HASH].indexes[INDEX_NAME_HASH]
    hash_engine_obj = index_obj.directory

    # --- INSERCIÓN (Hash) ---
    print(f"\n--- Prueba INSERCIÓN (Hash) ---")
    hash_engine_obj.read_count = 0; hash_engine_obj.write_count = 0
    start_time = time.perf_counter()
    print(f"Realizando {NUM_INSERTS} inserciones (orden aleatorio)...")
    for i, record_id in enumerate(inserted_ids_shuffled):
        engine.execute(f"INSERT INTO {TABLE_NAME_HASH} VALUES ({record_id}, 'Dato_{i}')")
    end_time = time.perf_counter()
    duration_ms = (end_time - start_time) * 1000
    reads = hash_engine_obj.read_count; writes = hash_engine_obj.write_count
    print(f"T: {duration_ms:.2f} ms | Prom: {(duration_ms / NUM_INSERTS):.4f} ms/ins | R: {reads} | W: {writes}")

    # --- BÚSQUEDA ESPECÍFICA (Hash) ---
    print(f"\n--- Prueba BÚSQUEDA ESPECÍFICA (Hash) ---")
    keys_to_search = random.sample(inserted_ids_ordered, min(NUM_SEARCHES, len(inserted_ids_ordered)))
    hash_engine_obj.read_count = 0; hash_engine_obj.write_count = 0
    search_times = []
    print(f"Realizando {len(keys_to_search)} búsquedas...")
    for key in keys_to_search:
        op_start = time.perf_counter()
        results = engine.execute(f"SELECT * FROM {TABLE_NAME_HASH} WHERE {INDEX_NAME_HASH} = {key}")
        op_end = time.perf_counter()
        search_times.append((op_end - op_start) * 1000)
    total_duration_ms = sum(search_times)
    reads = hash_engine_obj.read_count; writes = hash_engine_obj.write_count
    print(f"T: {total_duration_ms:.2f} ms | Prom: {(total_duration_ms / len(keys_to_search)):.4f} ms/bús | R: {reads} (Prom: {reads / len(keys_to_search):.2f}) | W: {writes}")

    # --- BÚSQUEDA POR RANGO (Hash - NO SOPORTADA) ---
    print(f"\n--- Prueba BÚSQUEDA POR RANGO (Hash) ---")
    print("Hashing no soporta búsqueda por rango.")

except Exception as e: print(f"Error Hash: {e}")
print("="*30)

# --- ISAM INDEX ---
print("\n" + "="*10 + " ISAM INDEX " + "="*10)
TABLE_NAME_ISAM = "tabla_isam"
INDEX_NAME_ISAM = "id"

SCHEMA_ISAM = f"{INDEX_NAME_ISAM} INT INDEX ISAM, data VARCHAR[50]"
try:
    print(f"Creando tabla '{TABLE_NAME_ISAM}' con definición ISAM...")
    
    engine.execute(f"CREATE TABLE {TABLE_NAME_ISAM} ({SCHEMA_ISAM})")
    table_obj_isam = engine.tables[TABLE_NAME_ISAM]
    print(f"Tabla '{TABLE_NAME_ISAM}' creada.")

    print(f"\n--- Prueba CONSTRUCCIÓN (ISAM Build) ---")
    print(f"Insertando {NUM_INSERTS} registros en tabla base (para build)...")
    
    for i, record_id in enumerate(inserted_ids_ordered):
         engine._insert_record_into_table(table_obj_isam, [record_id, f'Dato_{i}'], skip_isam=True)

    data_cap = 4 
    index_cap_l1 = 4 
    num_data_pages = (NUM_INSERTS + data_cap - 1) // data_cap
    num_l1_nodes = (num_data_pages + index_cap_l1 - 1) // index_cap_l1
    required_l2_capacity = num_l1_nodes
    build_index_capacity = max(64, required_l2_capacity) 

    print(f"Construyendo índice ISAM estático (ic={build_index_capacity}, dc={data_cap})...")
    start_time = time.perf_counter()
    
    index_obj = ISAMIndex.build_from_table(
        table_obj_isam,
        INDEX_NAME_ISAM,
        index_capacity=build_index_capacity, 
        data_capacity=data_cap
    )
    
    end_time = time.perf_counter()
    
    engine.tables[TABLE_NAME_ISAM].indexes[INDEX_NAME_ISAM] = index_obj
    isam_engine_obj = index_obj.engine # Acceder al motor ISAM
    duration_ms = (end_time - start_time) * 1000

    reads = isam_engine_obj.read_count
    writes = isam_engine_obj.write_count
    print(f"Tiempo total (build): {duration_ms:.2f} ms")
    print(f"Lecturas (tabla base, no contadas) | Escrituras (índice durante build): {writes}")

    # --- INSERCIÓN (ISAM - Overflow) ---
    NUM_ISAM_ADDS = NUM_INSERTS // 10
    print(f"\n--- Prueba INSERCIÓN (ISAM Overflow) ---")
    isam_engine_obj.read_count = 0; isam_engine_obj.write_count = 0
    start_time = time.perf_counter()
    print(f"Realizando {NUM_ISAM_ADDS} inserciones adicionales (overflow)...")
    additional_ids = list(range(end_id, end_id + NUM_ISAM_ADDS))
    random.shuffle(additional_ids)
    for i, record_id in enumerate(additional_ids):
        # Ahora INSERT INTO usa el índice ISAM construido
        engine.execute(f"INSERT INTO {TABLE_NAME_ISAM} VALUES ({record_id}, 'Overflow_{i}')")
    end_time = time.perf_counter()
    duration_ms = (end_time - start_time) * 1000
    reads = isam_engine_obj.read_count; writes = isam_engine_obj.write_count
    print(f"T: {duration_ms:.2f} ms | Prom: {(duration_ms / NUM_ISAM_ADDS):.4f} ms/ins | R: {reads} | W: {writes}")

    # --- BÚSQUEDA ESPECÍFICA (ISAM) ---
    print(f"\n--- Prueba BÚSQUEDA ESPECÍFICA (ISAM) ---")
    keys_to_search = random.sample(inserted_ids_ordered, min(NUM_SEARCHES // 2, len(inserted_ids_ordered)))
    keys_to_search += random.sample(additional_ids, min(NUM_SEARCHES // 2, len(additional_ids)))
    isam_engine_obj.read_count = 0; isam_engine_obj.write_count = 0
    search_times = []
    print(f"Realizando {len(keys_to_search)} búsquedas...")
    for key in keys_to_search:
        op_start = time.perf_counter()
        results = engine.execute(f"SELECT * FROM {TABLE_NAME_ISAM} WHERE {INDEX_NAME_ISAM} = {key}")
        op_end = time.perf_counter()
        search_times.append((op_end - op_start) * 1000)
    total_duration_ms = sum(search_times)
    reads = isam_engine_obj.read_count; writes = isam_engine_obj.write_count
    print(f"T: {total_duration_ms:.2f} ms | Prom: {(total_duration_ms / len(keys_to_search)):.4f} ms/bús | R: {reads} (Prom: {reads / len(keys_to_search):.2f}) | W: {writes}")

    # --- BÚSQUEDA POR RANGO (ISAM) ---
    print(f"\n--- Prueba BÚSQUEDA POR RANGO (ISAM) ---")
    isam_engine_obj.read_count = 0; isam_engine_obj.write_count = 0
    range_search_times = []
    print(f"Realizando {NUM_RANGE_SEARCHES} búsquedas (tamaño {RANGE_SIZE})...")
    for _ in range(NUM_RANGE_SEARCHES):
        start_range_key = random.randint(start_id, end_id - RANGE_SIZE - 1)
        end_range_key = start_range_key + RANGE_SIZE
        op_start = time.perf_counter()
        results = engine.execute(f"SELECT * FROM {TABLE_NAME_ISAM} WHERE {INDEX_NAME_ISAM} BETWEEN {start_range_key} AND {end_range_key}")
        op_end = time.perf_counter()
        range_search_times.append((op_end - op_start) * 1000)
    total_duration_ms = sum(range_search_times)
    reads = isam_engine_obj.read_count; writes = isam_engine_obj.write_count
    print(f"T: {total_duration_ms:.2f} ms | Prom: {(total_duration_ms / NUM_RANGE_SEARCHES):.4f} ms/bús | R: {reads} (Prom: {reads / NUM_RANGE_SEARCHES:.2f}) | W: {writes}")

except Exception as e: print(f"Error ISAM: {e}")
print("="*30)

# --- SEQUENTIAL FILE INDEX ---
print("\n" + "="*10 + " SEQUENTIAL FILE " + "="*10)
TABLE_NAME_SEQ = "tabla_seq"
INDEX_NAME_SEQ = "id"
SCHEMA_SEQ = f"{INDEX_NAME_SEQ} INT INDEX SEQ, data VARCHAR[50]"

SEQ_AUX_CAPACITY = 100
try:
    print(f"Creando tabla '{TABLE_NAME_SEQ}' (aux_capacity={SEQ_AUX_CAPACITY})...")
    engine.execute(f"CREATE TABLE {TABLE_NAME_SEQ} ({SCHEMA_SEQ})")
    print(f"Tabla '{TABLE_NAME_SEQ}' creada.")
    index_obj = engine.tables[TABLE_NAME_SEQ].indexes[INDEX_NAME_SEQ]
    seq_engine_obj = index_obj.engine
    seq_engine_obj.aux_capacity = SEQ_AUX_CAPACITY


    # --- INSERCIÓN (Sequential File) ---
    print(f"\n--- Prueba INSERCIÓN (Sequential File) ---")
    seq_engine_obj.read_count = 0; seq_engine_obj.write_count = 0
    start_time = time.perf_counter()
    print(f"Realizando {NUM_INSERTS} inserciones (orden aleatorio, con reconstrucciones)...")
    for i, record_id in enumerate(inserted_ids_shuffled):
        engine.execute(f"INSERT INTO {TABLE_NAME_SEQ} VALUES ({record_id}, 'Dato_{i}')")
    end_time = time.perf_counter()
    duration_ms = (end_time - start_time) * 1000
    reads = seq_engine_obj.read_count; writes = seq_engine_obj.write_count
    print(f"T: {duration_ms:.2f} ms | Prom: {(duration_ms / NUM_INSERTS):.4f} ms/ins | R: {reads} | W: {writes}")

    # --- BÚSQUEDA ESPECÍFICA (Sequential File) ---
    print(f"\n--- Prueba BÚSQUEDA ESPECÍFICA (Sequential File) ---")
    keys_to_search = random.sample(inserted_ids_ordered, min(NUM_SEARCHES, len(inserted_ids_ordered)))
    seq_engine_obj.read_count = 0; seq_engine_obj.write_count = 0
    search_times = []
    print(f"Realizando {len(keys_to_search)} búsquedas...")
    for key in keys_to_search:
        op_start = time.perf_counter()
        results = engine.execute(f"SELECT * FROM {TABLE_NAME_SEQ} WHERE {INDEX_NAME_SEQ} = {key}")
        op_end = time.perf_counter()
        search_times.append((op_end - op_start) * 1000)
    total_duration_ms = sum(search_times)
    reads = seq_engine_obj.read_count; writes = seq_engine_obj.write_count
    print(f"T: {total_duration_ms:.2f} ms | Prom: {(total_duration_ms / len(keys_to_search)):.4f} ms/bús | R: {reads} (Prom: {reads / len(keys_to_search):.2f}) | W: {writes}")

    # --- BÚSQUEDA POR RANGO (Sequential File) ---
    print(f"\n--- Prueba BÚSQUEDA POR RANGO (Sequential File) ---")
    seq_engine_obj.read_count = 0; seq_engine_obj.write_count = 0
    range_search_times = []
    print(f"Realizando {NUM_RANGE_SEARCHES} búsquedas (tamaño {RANGE_SIZE})...")
    for _ in range(NUM_RANGE_SEARCHES):
        start_range_key = random.randint(start_id, end_id - RANGE_SIZE - 1)
        end_range_key = start_range_key + RANGE_SIZE
        op_start = time.perf_counter()
        results = engine.execute(f"SELECT * FROM {TABLE_NAME_SEQ} WHERE {INDEX_NAME_SEQ} BETWEEN {start_range_key} AND {end_range_key}")
        op_end = time.perf_counter()
        range_search_times.append((op_end - op_start) * 1000)
    total_duration_ms = sum(range_search_times)
    reads = seq_engine_obj.read_count; writes = seq_engine_obj.write_count
    print(f"T: {total_duration_ms:.2f} ms | Prom: {(total_duration_ms / NUM_RANGE_SEARCHES):.4f} ms/bús | R: {reads} (Prom: {reads / NUM_RANGE_SEARCHES:.2f}) | W: {writes}")

except Exception as e: print(f"Error Sequential File: {e}")
print("="*30)

print("\nFin de los experimentos.")