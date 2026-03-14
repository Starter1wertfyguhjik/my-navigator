import streamlit as st
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import requests
from datetime import datetime, timedelta
import pytz
from streamlit_searchbox import st_searchbox

st.set_page_config(page_title="Smart Navigator MSK", layout="wide")

if "points_list" not in st.session_state:
    st.session_state.points_list = []
if "route_data" not in st.session_state:
    st.session_state.route_data = None

st.title("🚗 Умный Навигатор (Режим работы)")

# ---------------- ФУНКЦИЯ ПОИСКА ----------------
def address_search_provider(search_term: str):
    if not search_term or len(search_term) < 4:
        return []
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": search_term, "format": "json", "limit": 8, "countrycodes": "ru"}
    headers = {"User-Agent": "SmartNav_Searchbox_2026"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=5)
        return [x["display_name"] for x in r.json()]
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

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.header("📍 Настройка маршрута")

    st.write("**Откуда едем?**")
    start_addr = st_searchbox(
        address_search_provider,
        key="start_search",
        placeholder="Начните вводить адрес старта...",
        default="Москва, Красная площадь"
    )

    st.markdown("---")
    
    st.write("**Добавить точку назначения:**")
    new_point_addr = st_searchbox(
        address_search_provider,
        key="point_search",
        placeholder="Поиск адреса точки..."
    )
    
    # ВВОД ДИАПАЗОНА ВРЕМЕНИ
    st.write("🕒 Время работы точки:")
    col_time1, col_time2 = st.columns(2)
    with col_time1:
        open_h = st.number_input("Открытие", 0, 23, 9)
    with col_time2:
        close_h = st.number_input("Закрытие", 0, 23, 21)
    
    if st.button("➕ Добавить в список"):
        if new_point_addr:
            if open_h >= close_h:
                st.error("Время открытия должно быть меньше времени закрытия!")
            else:
                st.session_state.points_list.append({
                    "addr": new_point_addr, 
                    "open": open_h, 
                    "close": close_h
                })
                st.toast("Точка добавлена")
        else:
            st.warning("Выберите адрес!")

    if st.session_state.points_list:
        st.write("**Ваш список:**")
        for i, p in enumerate(st.session_state.points_list):
            st.caption(f"{i+1}. {p['addr'][:30]}... ({p['open']}:00 - {p['close']}:00)")
        
        if st.button("🗑 Очистить все"):
            st.session_state.points_list = []
            st.rerun()

    st.markdown("---")
    btn_calc = st.button("🚀 ПОСТРОИТЬ МАРШРУТ", use_container_width=True)

# ---------------- УМНАЯ ОПТИМИЗАЦИЯ С УЧЕТОМ ОКНА РАБОТЫ ----------------
def optimize_route(start, points_list):
    speed = 30
    tz_moscow = pytz.timezone('Europe/Moscow')
    current_time = datetime.now(tz_moscow)
    
    current_pos = start
    ordered = []
    temp = points_list[:]

    while temp:
        best = None
        min_score = float('inf')
        
        for p in temp:
            dist = geodesic(current_pos, (p["lat"], p["lon"])).km
            travel_hours = dist / speed
            arrival_time = current_time + timedelta(hours=travel_hours)
            
            # Определяем границы работы точки в этот день
            open_time = arrival_time.replace(hour=p["open"], minute=0, second=0)
            close_time = arrival_time.replace(hour=p["close"], minute=0, second=0)
            
            # ЛОГИКА ШТРАФОВ (SCORE)
            if arrival_time > close_time:
                # Мы опоздали (огромный штраф)
                wait_penalty = 5000 + dist
            elif arrival_time < open_time:
                # Мы приехали раньше (штраф за ожидание открытия)
                wait_hours = (open_time - arrival_time).total_seconds() / 3600
                wait_penalty = dist + (wait_hours * 20) 
            else:
                # Мы попали в окно работы (приоритет тем, кто скоро закроется)
                hours_to_close = (close_time - arrival_time).total_seconds() / 3600
                wait_penalty = dist + (hours_to_close * 5)

            if wait_penalty < min_score:
                min_score = wait_penalty
                best = p

        # Фиксируем выбор
        chosen = best
        dist_to_chosen = geodesic(current_pos, (chosen["lat"], chosen["lon"])).km
        travel_time = timedelta(hours=dist_to_chosen / speed)
        
        # Обновляем текущее время: время в пути + если приехали раньше, ждем открытия
        current_time += travel_time
        open_dt = current_time.replace(hour=chosen["open"], minute=0)
        if current_time < open_dt:
            current_time = open_dt # Ждем до открытия
            
        current_pos = (chosen["lat"], chosen["lon"])
        ordered.append(chosen)
        temp.remove(chosen)

    return ordered, datetime.now(tz_moscow).strftime("%H:%M")

# ---------------- ЛОГИКА РАСЧЕТА ----------------
if btn_calc:
    if not start_addr or not st.session_state.points_list:
        st.error("Заполните старт и добавьте точки!")
    else:
        with st.spinner("Геокодируем..."):
            start_coords = get_coordinates_cached(start_addr)
            if start_coords:
                points_data = []
                for p in st.session_state.points_list:
                    coords = get_coordinates_cached(p["addr"])
                    if coords:
                        points_data.append({
                            "lat": coords[0], "lon": coords[1], 
                            "name": coords[2], "open": p["open"], "close": p["close"]
                        })
                
                if points_data:
                    ordered, msk_time = optimize_route((start_coords[0], start_coords[1]), points_data)
                    st.session_state.route_data = {
                        "start": start_coords, "stops": ordered, "msk_start_time": msk_time
                    }
                else:
                    st.error("Координаты точек не найдены.")
            else:
                st.error("Старт не найден.")

# ---------------- ВЫВОД ----------------
if st.session_state.route_data:
    data = st.session_state.route_data
    s_lat, s_lon, s_name = data["start"]
    stops = data["stops"]

    st.info(f"🕒 Время выезда: {data['msk_start_time']} (МСК)")

    m = folium.Map(location=[s_lat, s_lon], zoom_start=11)
    all_pts = [(s_lat, s_lon)] + [(p['lat'], p['lon']) for p in stops] + [(s_lat, s_lon)]
    folium.PolyLine(all_pts, color="#2980b9", weight=5).add_to(m)
    folium.Marker([s_lat, s_lon], icon=folium.Icon(color="red", icon="home")).add_to(m)

    for i, p in enumerate(stops, 1):
        folium.Marker(
            [p["lat"], p["lon"]], 
            tooltip=f"{i}. {p['name']} ({p['open']}:00-{p['close']}:00)",
            icon=folium.Icon(color="blue")
        ).add_to(m)

    st_folium(m, width="100%", height=500, returned_objects=[], key="map_final")

    # Кнопка Google
    waypoints = "|".join([f"{p['lat']},{p['lon']}" for p in stops])
    google_url = f"https://www.google.com/maps/dir/?api=1&origin={s_lat},{s_lon}&destination={s_lat},{s_lon}&waypoints={waypoints}&travelmode=driving"

    st.markdown(f"""
        <a href="{google_url}" target="_blank" style="text-decoration:none;">
            <div style="background:#28a745;color:white;padding:20px;text-align:center;border-radius:15px;font-size:24px;font-weight:bold;">
                🚀 ОТКРЫТЬ В GOOGLE MAPS
            </div>
        </a>
    """, unsafe_allow_html=True)

    with st.expander("📝 Детальный план"):
        for i, p in enumerate(stops, 1):
            st.write(f"{i}. **{p['name']}** — работает с {p['open']}:00 до {p['close']}:00")
