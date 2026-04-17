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

st.title("🚗 Умный Навигатор (Режим работы + Дороги)")

# ---------------- ФУНКЦИЯ ПОИСКА ----------------
import time

@st.cache_data(ttl=3600)  # Кэшируем результаты поиска на час
def search_photon(search_term):
    # Используем Photon API (он быстрее и реже выдает 429)
    url = "https://photon.komoot.io/api/"
    params = {
        "q": search_term,
        "limit": 10,
        "lang": "ru"
    }
    try:
        r = requests.get(url, params=params, timeout=5)
        if r.status_code == 200:
            data = r.json()
            features = data.get("features", [])
            results = []
            for f in features:
                p = f.get("properties", {})
                # Собираем красивое название: Город, Улица, Номер
                name_parts = [p.get("city"), p.get("street"), p.get("housenumber")]
                full_name = ", ".join([x for x in name_parts if x])
                if not full_name:
                    full_name = p.get("name", "Неизвестное место")
                results.append(full_name)
            return list(set(results)) # Убираем дубликаты
        return []
    except:
        return []

def address_search_provider(search_term: str):
    if not search_term or len(search_term) < 3:
        return []
    
    # Небольшая пауза (0.3 сек), чтобы не спамить при быстром наборе
    time.sleep(0.3)
    
    return search_photon(search_term)

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

# ---------------- ЗАПРОС РЕАЛЬНЫХ ДОРОГ (OSRM) ----------------
def get_osrm_route(start_coords, end_coords):
    """
    Запрашивает реальное расстояние по дорогам и время в пути у бесплатного OSRM API.
    Координаты передаются в формате (lat, lon). OSRM ожидает lon, lat.
    """
    url = f"http://router.project-osrm.org/route/v1/driving/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}?overview=false"
    try:
        r = requests.get(url, timeout=3)
        data = r.json()
        if data.get("code") == "Ok":
            dist_km = data["routes"][0]["distance"] / 1000.0
            duration_sec = data["routes"][0]["duration"]
            return dist_km, duration_sec / 3600.0  # возвращаем км и часы
    except Exception:
        pass
    
    # Фолбэк (если OSRM недоступен): считаем по прямой + скорость 30 км/ч
    dist_km = geodesic(start_coords, end_coords).km
    return dist_km, dist_km / 30.0

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

# ---------------- УМНАЯ ОПТИМИЗАЦИЯ С УЧЕТОМ ДОРОГ И ОКНА РАБОТЫ ----------------
def optimize_route(start, points_list):
    tz_moscow = pytz.timezone('Europe/Moscow')
    current_time = datetime.now(tz_moscow)
    
    current_pos = start
    ordered = []
    temp = points_list[:]

    while temp:
        best = None
        min_score = float('inf')
        best_travel_time = 0
        
        for p in temp:
            # Считаем РЕАЛЬНОЕ время и расстояние по дорогам
            dist, travel_hours = get_osrm_route(current_pos, (p["lat"], p["lon"]))
            
            arrival_time = current_time + timedelta(hours=travel_hours)
            
            open_time = arrival_time.replace(hour=p["open"], minute=0, second=0)
            close_time = arrival_time.replace(hour=p["close"], minute=0, second=0)
            
            # ЛОГИКА ОЦЕНКИ (SCORE): Чем меньше очков, тем выгоднее ехать
            # Базовая цена - это время в пути в минутах (расход топлива и времени)
            score = travel_hours * 60 
            
            if arrival_time > close_time:
                # Жесткий штраф за опоздание (точка закроется)
                score += 10000 
            elif arrival_time < open_time:
                # Приехали раньше - ждем. Простой машины - это потеря времени, но топливо не тратится.
                wait_minutes = (open_time - arrival_time).total_seconds() / 60
                score += wait_minutes * 0.5  # Штраф за ожидание меньше, чем за езду
            else:
                # Попали в рабочее окно!
                # Даем приоритет тем точкам, которые скоро закроются (чтобы успеть)
                minutes_to_close = (close_time - arrival_time).total_seconds() / 60
                if minutes_to_close < 60:
                    score -= (60 - minutes_to_close)  # "Горящие" точки забираем быстрее
            
            # Ищем точку с минимальным "штрафом"
            if score < min_score:
                min_score = score
                best = p
                best_travel_time = travel_hours

        # Фиксируем выбор
        chosen = best
        
        # Обновляем время (добавляем время в пути)
        current_time += timedelta(hours=best_travel_time)
        
        # Если приехали раньше открытия, стоим и ждем
        open_dt = current_time.replace(hour=chosen["open"], minute=0, second=0)
        if current_time < open_dt:
            current_time = open_dt
            
        current_pos = (chosen["lat"], chosen["lon"])
        ordered.append(chosen)
        temp.remove(chosen)

    return ordered, datetime.now(tz_moscow).strftime("%H:%M")

# ---------------- ЛОГИКА РАСЧЕТА ----------------
if btn_calc:
    if not start_addr or not st.session_state.points_list:
        st.error("Заполните старт и добавьте точки!")
    else:
        with st.spinner("Рассчитываем маршрут по реальным дорогам..."):
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

    # Исправленная ссылка на Google Maps (API Directions)
    waypoints = "|".join([f"{p['lat']},{p['lon']}" for p in stops])
    google_url = f"https://www.google.com/maps/dir/?api=1&origin={s_lat},{s_lon}&destination={s_lat},{s_lon}&waypoints={waypoints}&travelmode=driving"

    st.markdown(f"""
        <a href="{google_url}" target="_blank" style="text-decoration:none;">
            <div style="background:#28a745;color:white;padding:20px;text-align:center;border-radius:15px;font-size:24px;font-weight:bold;margin-bottom:20px;">
                🚀 ОТКРЫТЬ В GOOGLE MAPS
            </div>
        </a>
    """, unsafe_allow_html=True)

    with st.expander("📝 Детальный план (порядок объезда)"):
        st.write(f"**Старт:** {s_name}")
        for i, p in enumerate(stops, 1):
            st.write(f"{i}. **{p['name']}** — работает с {p['open']}:00 до {p['close']}:00")
        st.write(f"**Финиш:** Возврат на старт")
