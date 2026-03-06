import streamlit as st
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import requests
import time

# --- НАСТРОЙКИ ---
MAPBOX_TOKEN = "ВАШ_ТОКЕН_ЗДЕСЬ"  # <-- ВСТАВЬ СЮДА СВОЙ ТОКЕН МАРBOX

st.set_page_config(page_title="Pro Navigator v2.0", layout="wide")

# Инициализация хранилища данных, чтобы ничего не пропадало при кликах
if 'route_data' not in st.session_state:
    st.session_state.route_data = None

st.title("🚗 Умный Навигатор: Реальные дороги + Пробки")

# --- БОКОВАЯ ПАНЕЛЬ ---
with st.sidebar:
    st.header("📍 Маршрут")
    start_addr = st.text_input("Ваш адрес (Старт/Финиш)", "Москва, Красная площадь")
    dest_raw = st.text_area("Точки через точку с запятой (;)",
                            "Москва, Тверская 1; Москва, Новый Арбат 10; Москва, ВДНХ")

    btn_calc = st.button("🗺️ Построить оптимальный путь")
    st.write("---")
    st.info("Приложение найдет кратчайший путь по дорогам, чтобы сэкономить ваше время и бензин.")


# --- ФУНКЦИИ ---

def get_coordinates(address):
    """Превращает текстовый адрес в (lat, lon)"""
    try:
        geolocator = Nominatim(user_agent="my_final_nav_app_2026")
        loc = geolocator.geocode(address, timeout=10)
        return (loc.latitude, loc.longitude, loc.address) if loc else None
    except:
        return None


def get_mapbox_route(points):
    """Запрашивает реальный путь по дорогам у Mapbox с учетом трафика"""
    if MAPBOX_TOKEN == "ВАШ_ТОКЕН_ЗДЕСЬ":
        return None

    # Формат для Mapbox: долгота,широта
    coords_str = ";".join([f"{p[1]},{p[0]}" for p in points])
    url = f"https://api.mapbox.com/directions/v5/mapbox/driving-traffic/{coords_str}"
    params = {
        "access_token": MAPBOX_TOKEN,
        "geometries": "geojson",
        "overview": "full"
    }
    try:
        r = requests.get(url, params=params)
        data = r.json()
        if "routes" in data:
            return data["routes"][0]["geometry"]["coordinates"]
    except:
        return None
    return None


# --- ЛОГИКА ВЫЧИСЛЕНИЙ ---
if btn_calc:
    with st.spinner("Считаем лучший маршрут по дорогам..."):
        start_res = get_coordinates(start_addr)

        if start_res:
            points_list = []
            for a in dest_raw.split(";"):
                coords = get_coordinates(a.strip())
                if coords:
                    points_list.append({"lat": coords[0], "lon": coords[1], "name": coords[2]})

            # Сортировка "Ближайший сосед" для оптимизации порядка
            current_pos = (start_res[0], start_res[1])
            ordered = []
            temp_pts = points_list[:]

            while temp_pts:
                next_pt = min(temp_pts, key=lambda x: geodesic(current_pos, (x['lat'], x['lon'])).km)
                ordered.append(next_pt)
                current_pos = (next_pt['lat'], next_pt['lon'])
                temp_pts.remove(next_pt)

            # Сохраняем в сессию
            st.session_state.route_data = {
                "start": start_res,
                "ordered_stops": ordered
            }
        else:
            st.error("Не удалось найти адрес старта!")

# --- ОТРИСОВКА КАРТЫ И ИНТЕРФЕЙСА ---
if st.session_state.route_data:
    data = st.session_state.route_data
    s_lat, s_lon, s_full_name = data["start"]
    stops = data["ordered_stops"]

    # Создаем список всех ключевых точек (Старт -> Остановки -> Финиш)
    all_key_coords = [(s_lat, s_lon)] + [(p['lat'], p['lon']) for p in stops] + [(s_lat, s_lon)]

    # 1. Получаем путь по дорогам от Mapbox
    road_geometry = get_mapbox_route(all_key_coords)

    # 2. Создаем карту
    m = folium.Map(location=[s_lat, s_lon], zoom_start=12)

    # Добавляем слой пробок Google для визуализации
    folium.TileLayer(
        tiles='https://{s}.google.com/vt/lyrs=m@221097413,traffic&x={x}&y={y}&z={z}',
        attr='Google Traffic',
        name='Пробки',
        overlay=True,
        subdomains=['mt0', 'mt1', 'mt2', 'mt3']
    ).add_to(m)

    # 3. Рисуем линию маршрута
    if road_geometry:
        # Инвертируем [lon, lat] в [lat, lon]
        folium_path = [[p[1], p[0]] for p in road_geometry]
        folium.PolyLine(folium_path, color="#FF0000", weight=6, opacity=0.8).add_to(m)
    else:
        # Если Mapbox не сработал — рисуем прямые линии
        folium.PolyLine(all_key_coords, color="blue", weight=3, dash_array='10').add_to(m)
        st.warning("Маршрут построен по прямой. Вставьте API-ключ Mapbox для дорог.")

    # 4. Ставим маркеры
    folium.Marker([s_lat, s_lon], tooltip="СТАРТ/ФИНИШ", icon=folium.Icon(color='red', icon='home')).add_to(m)
    for i, p in enumerate(stops, 1):
        folium.Marker([p['lat'], p['lon']], tooltip=f"{i}. {p['name']}", icon=folium.Icon(color='blue')).add_to(m)

    # ВЫВОД КАРТЫ
    st_folium(m, width="100%", height=500, key="nav_map")

    # 5. Кнопка для телефона (Google Maps)
    origin = f"{s_lat},{s_lon}"
    waypoints = "|".join([f"{p['lat']},{p['lon']}" for p in stops])

    google_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={origin}&waypoints={waypoints}&travelmode=driving"

    st.markdown(f"""
    <a href="{google_url}" style="text-decoration: none;">
    <div style="
    background-color:#28a745;
    color:white;
    padding:20px;
    text-align:center;
    border-radius:15px;
    font-size:22px;
    font-weight:bold;
    cursor:pointer;">
    🚀 ЗАПУСТИТЬ НАВИГАТОР
    </div>
    </a>
    """, unsafe_allow_html=True)

    # Список остановок текстом
    with st.expander("Посмотреть текстовый план маршрута"):
        st.write(f"🚩 **Начало:** {s_full_name}")
        for i, p in enumerate(stops, 1):
            st.write(f"{i}. {p['name']}")
        st.write(f"🏁 **Возврат:** {s_full_name}")




