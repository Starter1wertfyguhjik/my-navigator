import streamlit as st
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import requests
from datetime import datetime, timedelta
import pytz  # Часовые пояса

st.set_page_config(page_title="Smart Navigator MSK", layout="wide")

if "route_data" not in st.session_state:
    st.session_state.route_data = None

st.title("🚗 Умный Навигатор")

# ---------------- УЛУЧШЕННАЯ ФУНКЦИЯ ПОДСКАЗОК ----------------
def address_search(query):
    if len(query) < 4:  # Ищем только когда введено 4+ символа
        return []
    url = "https://nominatim.openstreetmap.org/search"
    # Добавляем заголовки и фильтр по стране для точности и скорости
    params = {
        "q": query, 
        "format": "json", 
        "limit": 5,
        "countrycodes": "ru"
    }
    headers = {"User-Agent": "SmartNavApp_v2_2026"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=5)
        data = r.json()
        return [x["display_name"] for x in data]
    except:
        return []

# ---------------- КЭШИРОВАННЫЙ ГЕОКОДЕР ----------------
@st.cache_data
def get_coordinates_cached(address):
    try:
        geolocator = Nominatim(user_agent="smart_nav_full_2026")
        loc = geolocator.geocode(address, timeout=10)
        if loc:
            return loc.latitude, loc.longitude, loc.address
    except:
        pass
    return None

# ---------------- SIDEBAR (ОБНОВЛЕННЫЙ БЛОК ПОИСКА) ----------------
with st.sidebar:
    st.header("📍 Маршрут")

    # Улучшенный ввод старта
    start_query = st.text_input("Введите старт (минимум 4 символа)", "Москва, Красная площадь")
    suggestions = address_search(start_query) if start_query else []
    
    if suggestions:
        start_addr = st.selectbox("Выберите уточненный адрес из списка:", suggestions)
    else:
        start_addr = start_query

    dest_raw = st.text_area(
        "Точки (Адрес | Час закрытия)",
        "Москва, Тверская 1 | 18\nМосква, Новый Арбат 10 | 21\nМосква, ВДНХ",
        height=150
    )

    btn_calc = st.button("Построить маршрут")
    st.info("Формат: 'Адрес | 18' (точка закроется в 18:00 по МСК)")

# ---------------- ПАРСИНГ ТОЧЕК ----------------
def parse_points(text):
    points = []
    lines = text.split("\n")
    for line in lines:
        if not line.strip(): continue
        if "|" in line:
            parts = line.split("|")
            addr = parts[0].strip()
            try:
                close = int(parts[1].strip())
            except:
                close = None
        else:
            addr = line.strip()
            close = None
        points.append((addr, close))
    return points

# ---------------- УМНАЯ ОПТИМИЗАЦИЯ (МСК + СРОЧНОСТЬ) ----------------
def optimize_route(start, points_list):
    speed = 30  # средняя скорость км/ч
    
    tz_moscow = pytz.timezone('Europe/Moscow')
    now = datetime.now(tz_moscow)
    
    current_pos = start
    ordered = []
    temp = points_list[:]

    while temp:
        best = None
        min_score = float('inf')

        for p in temp:
            dist = geodesic(current_pos, (p["lat"], p["lon"])).km
            travel_hours = dist / speed
            arrival = now + timedelta(hours=travel_hours)

            if p["close"]:
                close_time = now.replace(hour=p["close"], minute=0, second=0, microsecond=0)
                remaining = (close_time - arrival).total_seconds() / 3600
                
                if remaining < 0:
                    score = 2000 + dist 
                else:
                    score = dist + (remaining * 10)
            else:
                score = dist + 200

            if score < min_score:
                min_score = score
                best = p

        chosen = best if best else temp[0]
        dist_to_chosen = geodesic(current_pos, (chosen["lat"], chosen["lon"])).km
        
        now += timedelta(hours=dist_to_chosen / speed)
        current_pos = (chosen["lat"], chosen["lon"])
        ordered.append(chosen)
        temp.remove(chosen)

    return ordered, datetime.now(tz_moscow).strftime("%H:%M")

# ---------------- ЛОГИКА ПРИ НАЖАТИИ КНОПКИ ----------------
if btn_calc:
    # Используем адрес, выбранный из выпадающего списка или введенный вручную
    start_coords = get_coordinates_cached(start_addr)
    if not start_coords:
        st.error(f"Не найден адрес старта: {start_addr}")
    else:
        parsed = parse_points(dest_raw)
        points_data = []
        for addr, close in parsed:
            coords = get_coordinates_cached(addr)
            if coords:
                points_data.append({
                    "lat": coords[0],
                    "lon": coords[1],
                    "name": coords[2],
                    "close": close
                })
        
        if points_data:
            ordered_stops, msk_time = optimize_route((start_coords[0], start_coords[1]), points_data)
            st.session_state.route_data = {
                "start": start_coords,
                "stops": ordered_stops,
                "msk_start_time": msk_time
            }
        else:
            st.error("Не удалось найти координаты для точек маршрута")

# ---------------- КАРТА И ВЫВОД ----------------
if st.session_state.route_data:
    data = st.session_state.route_data
    s_lat, s_lon, s_name = data["start"]
    stops = data["stops"]

    st.subheader(f"🕒 Время выезда по Москве: {data['msk_start_time']}")

    all_coords = [(s_lat, s_lon)] + [(p['lat'], p['lon']) for p in stops] + [(s_lat, s_lon)]

    m = folium.Map(location=[s_lat, s_lon], zoom_start=12)
    folium.PolyLine(all_coords, color="#2980b9", weight=5, opacity=0.7).add_to(m)

    folium.Marker([s_lat, s_lon], tooltip="СТАРТ / ФИНИШ", icon=folium.Icon(color="red", icon="home")).add_to(m)

    for i, p in enumerate(stops, 1):
        label = p["name"]
        if p["close"]:
            label += f" | Закрывается в {p['close']}:00"
        folium.Marker([p["lat"], p["lon"]], tooltip=f"{i}. {label}", icon=folium.Icon(color="blue")).add_to(m)

    st_folium(m, width="100%", height=500, returned_objects=[], key="map_view")

    # ---------------- КНОПКА НАВИГАЦИИ ----------------
    origin = f"{s_lat},{s_lon}"
    waypoints = "|".join([f"{p['lat']},{p['lon']}" for p in stops])
    google_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={origin}&waypoints={waypoints}&travelmode=driving"

    st.markdown(
        f"""
        <a href="{google_url}" target="_blank" style="text-decoration:none;">
        <div style="
            background:#28a745;
            color:white;
            padding:20px;
            text-align:center;
            border-radius:15px;
            font-size:24px;
            font-weight:bold;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
            margin-top: 20px;">
            🚀 ОТКРЫТЬ В НАВИГАТОРЕ
        </div>
        </a>
        """,
        unsafe_allow_html=True
    )

    with st.expander("Посмотреть текстовый план маршрута"):
        st.write(f"🚩 **Начало:** {s_name}")
        for i, p in enumerate(stops, 1):
            time_tag = f" — 🕒 до {p['close']}:00" if p["close"] else ""
            st.write(f"{i}. {p['name']}{time_tag}")
        st.write(f"🏁 **Возврат:** {s_name}")
