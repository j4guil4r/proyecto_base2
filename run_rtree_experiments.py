# run_rtree_experiments.py
import time
import shutil
import os
import random
from src.core.engine import DatabaseEngine

# --- 1. CONFIGURACIÓN ---
DB_DIR = 'experimental_data_rtree' # Usar un directorio separado para RTree
TABLE_NAME = "locations"
INDEX_NAME = "coords" # Nombre de la columna con el índice RTree
# Asegúrate que el schema coincida con tu engine y parser
# El tipo ARRAY[FLOAT] es crucial
SCHEMA = f"id INT, name VARCHAR[50], {INDEX_NAME} ARRAY[FLOAT] INDEX RTREE"

# Número de operaciones para las pruebas
NUM_INSERTS = 1000
NUM_RADIUS_SEARCHES = 100 # Búsquedas por cada radio
NUM_KNN_SEARCHES = 100    # Búsquedas por cada K

# Parámetros para las búsquedas RTree
RADII_TO_TEST = [0.1, 1.0, 5.0, 10.0] # Diferentes radios a probar
K_VALUES_TO_TEST = [1, 5, 10, 20]     # Diferentes valores de K a probar

# Rango de coordenadas para los datos sintéticos (ej. 0.0 a 100.0)
COORD_MIN = 0.0
COORD_MAX = 100.0

print(f"Limpiando directorio de datos: {DB_DIR}")
shutil.rmtree(DB_DIR, ignore_errors=True)
os.makedirs(DB_DIR, exist_ok=True)

print("Inicializando Database Engine...")
engine = DatabaseEngine(data_dir=DB_DIR)

# --- 2. CREACIÓN DE TABLA E ÍNDICE R-Tree ---
print("\n" + "="*10 + " R-TREE " + "="*10)
try:
    print(f"Creando tabla '{TABLE_NAME}' con índice R-Tree...")
    engine.execute(f"CREATE TABLE {TABLE_NAME} ({SCHEMA})")
    print(f"Tabla '{TABLE_NAME}' creada.")

    # Validar que la tabla y el índice existen
    if TABLE_NAME not in engine.tables or INDEX_NAME not in engine.tables[TABLE_NAME].indexes:
        raise RuntimeError(f"Tabla o índice R-Tree no encontrado después de crear.")
    rtree_index_obj = engine.tables[TABLE_NAME].indexes[INDEX_NAME] # Obtener el objeto índice

    # --- 3. PRUEBA DE INSERCIÓN (R-Tree Add) ---
    print(f"\n--- Prueba INSERCIÓN (R-Tree) ---")
    insert_times = []
    inserted_points = [] # Guardar puntos para usarlos en búsquedas
    start_time = time.perf_counter()
    print(f"Realizando {NUM_INSERTS} inserciones...")
    for i in range(NUM_INSERTS):
        # Generar coordenadas 2D aleatorias
        coord1 = round(random.uniform(COORD_MIN, COORD_MAX), 6)
        coord2 = round(random.uniform(COORD_MIN, COORD_MAX), 6)
        point = (coord1, coord2)
        inserted_points.append(point)

        op_start = time.perf_counter()
        # Usar formato de tupla como string para INSERT SQL
        engine.execute(f"INSERT INTO {TABLE_NAME} VALUES ({i}, 'Lugar_{i}', '({point[0]},{point[1]})')")
        op_end = time.perf_counter()
        insert_times.append((op_end - op_start) * 1000)
    end_time = time.perf_counter() # Tiempo total (incluye bucle)
    total_duration_ms = sum(insert_times) # Suma de tiempos de operaciones individuales

    print(f"T: {total_duration_ms:.2f} ms | Prom: {(total_duration_ms / NUM_INSERTS):.4f} ms/ins")

    # --- 4. PRUEBA DE BÚSQUEDA POR RADIO (R-Tree radius_search) ---
    print(f"\n--- Prueba BÚSQUEDA POR RADIO (R-Tree) ---")
    print(f"Realizando {NUM_RADIUS_SEARCHES} búsquedas por cada radio...")
    # Diccionario para guardar tiempos promedio por radio
    radius_search_avg_times: dict[float, float] = {}

    for radius in RADII_TO_TEST:
        radius_times = []
        for _ in range(NUM_RADIUS_SEARCHES):
            # Elegir un punto de consulta aleatorio
            query_coord1 = round(random.uniform(COORD_MIN, COORD_MAX), 6)
            query_coord2 = round(random.uniform(COORD_MIN, COORD_MAX), 6)
            point_str = f"({query_coord1},{query_coord2})" # Formato para SQL

            op_start = time.perf_counter()
            # Ejecutar la consulta SQL de búsqueda por radio [cite: 46]
            results = engine.execute(f"SELECT * FROM {TABLE_NAME} WHERE {INDEX_NAME} IN ({point_str}, {radius})")
            op_end = time.perf_counter()
            radius_times.append((op_end - op_start) * 1000)

        avg_time = sum(radius_times) / len(radius_times)
        radius_search_avg_times[radius] = avg_time
        print(f"Radio={radius:.2f}: Prom={avg_time:.4f} ms/búsqueda")

    # --- 5. PRUEBA DE K-VECINOS CERCANOS (R-Tree knn_search) ---
    print(f"\n--- Prueba K-VECINOS CERCANOS (KNN - R-Tree) ---")
    print(f"Realizando {NUM_KNN_SEARCHES} búsquedas por cada K...")
    # Diccionario para guardar tiempos promedio por K
    knn_search_avg_times: dict[int, float] = {}

    # Nota: El parser actual no soporta KNN, llamamos al método del índice directamente.
    print("(Llamando directamente a knn_search del índice)")
    for k in K_VALUES_TO_TEST:
        knn_times = []
        for _ in range(NUM_KNN_SEARCHES):
            # Elegir un punto de consulta aleatorio
            query_coord1 = round(random.uniform(COORD_MIN, COORD_MAX), 6)
            query_coord2 = round(random.uniform(COORD_MIN, COORD_MAX), 6)
            query_point = (query_coord1, query_coord2)

            op_start = time.perf_counter()
            # Llamar directamente al método knn_search del objeto índice
            rids = rtree_index_obj.knn_search(query_point, k)
            # Opcional: Recuperar los registros si se necesita verificar algo
            # results = [engine.tables[TABLE_NAME].get_record(rid) for rid in rids]
            op_end = time.perf_counter()
            knn_times.append((op_end - op_start) * 1000)

        avg_time = sum(knn_times) / len(knn_times)
        knn_search_avg_times[k] = avg_time
        print(f"K={k}: Prom={avg_time:.4f} ms/búsqueda")

except Exception as e:
    print(f"Error durante las pruebas de R-Tree: {e}")

print("="*30)
print("\nFin de los experimentos con R-Tree.")