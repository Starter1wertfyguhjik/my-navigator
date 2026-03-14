import streamlit as st
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import requests
from datetime import datetime, timedelta
import pytz
from streamlit_searchbox import st_searchbox  # Основной инструмент для вашей задачи

st.set_page_config(page_title="Smart Navigator MSK", layout="wide")

# Инициализируем хранилище точек в сессии, чтобы они не пропадали
if "points_list" not in st.session_state:
    st.session_state.points_list = []
if "route_data" not in st.session_state:
    st.session_state.route_data = None

st.title("🚗 Умный Навигатор")

# ---------------- ФУНКЦИЯ ПОИСКА ДЛЯ АВТОКОМПЛИТА ----------------
def address_search_provider(search_term: str):
    if not search_term or len(search_term) < 4:
        return []
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": search_term,
        "format": "json",
        "limit": 8,
        "countrycodes": "ru"
    }
    headers = {"User-Agent": "SmartNav_Searchbox_2026"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=5)
        # Возвращаем список строк для выпадающего меню
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

    # ЖИВОЙ ПОИСК ДЛЯ СТАРТА
    st.write("**Откуда едем?**")
    start_addr = st_searchbox(
        address_search_provider,
        key="start_search",
        placeholder="Начните вводить адрес старта...",
        default="Москва, Красная площадь"
    )

    st.markdown("---")
    
    # ЖИВОЙ ПОИСК ДЛЯ ТОЧЕК
    st.write("**Добавить точку в маршрут:**")
    new_point_addr = st_searchbox(
        address_search_provider,
        key="point_search",
        placeholder="Поиск адреса точки..."
    )
    
    col1, col2 = st.columns([1, 1])
    with col1:
        close_h = st.number_input("До скольки работает?", 0, 23, 18, help="Час закрытия (0-23)")
    with col2:
        st.write("") # Отступ
        if st.button("➕ Добавить"):
            if new_point_addr:
                st.session_state.points_list.append({"addr": new_point_addr, "close": close_h})
                st.toast(f"Добавлено: {new_point_addr[:30]}...")
            else:
                st.warning("Сначала выберите адрес!")

    # Список уже добавленных точек с возможностью очистки
    if st.session_state.points_list:
        st.write("**Текущие точки:**")
        for i, p in enumerate(st.session_state.points_list):
            st.caption(f"{i+1}. {p['addr'][:40]}... (до {p['close']}:00)")
        
        if st.button("🗑 Очистить все точки"):
            st.session_state.points_list = []
            st.session_state.route_data = None
            st.rerun()

    st.markdown("---")
    btn_calc = st.button("🚀 ПОСТРОИТЬ МАРШРУТ", use_container_width=True)

# ---------------- ЛОГИКА ОПТИМИЗАЦИИ ----------------
def optimize_route(start, points_list):
    speed = 30
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

# ---------------- ОБРАБОТКА РАСЧЕТА ----------------
if btn_calc:
    if not start_addr:
        st.error("Укажите адрес старта!")
    elif not st.session_state.points_list:
        st.error("Добавьте хотя бы одну точку!")
    else:
        with st.spinner("Геокодируем адреса..."):
            start_coords = get_coordinates_cached(start_addr)
            if start_coords:
                points_data = []
                for p in st.session_state.points_list:
                    coords = get_coordinates_cached(p["addr"])
                    if coords:
                        points_data.append({
                            "lat": coords[0], "lon": coords[1], 
                            "name": coords[2], "close": p["close"]
                        })
                
                if points_data:
                    ordered, msk_time = optimize_route((start_coords[0], start_coords[1]), points_data)
                    st.session_state.route_data = {
                        "start": start_coords,
                        "stops": ordered,
                        "msk_start_time": msk_time
                    }
                else:
                    st.error("Не удалось найти координаты точек.")
            else:
                st.error("Не удалось найти старт.")

# ---------------- ВЫВОД КАРТЫ И НАВИГАЦИИ ----------------
if st.session_state.route_data:
    data = st.session_state.route_data
    s_lat, s_lon, s_name = data["start"]
    stops = data["stops"]

    st.subheader(f"🕒 Время отправления (МСК): {data['msk_start_time']}")

    all_coords = [(s_lat, s_lon)] + [(p['lat'], p['lon']) for p in stops] + [(s_lat, s_lon)]
    m = folium.Map(location=[s_lat, s_lon], zoom_start=12)
    folium.PolyLine(all_coords, color="#2980b9", weight=5, opacity=0.7).add_to(m)
    folium.Marker([s_lat, s_lon], icon=folium.Icon(color="red", icon="home")).add_to(m)

    for i, p in enumerate(stops, 1):
        label = f"{i}. {p['name']}" + (f" | до {p['close']}:00" if p['close'] else "")
        folium.Marker([p["lat"], p["lon"]], tooltip=label, icon=folium.Icon(color="blue")).add_to(m)

    st_folium(m, width="100%", height=500, returned_objects=[], key="map_view")

    # Кнопка навигации
    origin = f"{s_lat},{s_lon}"
    waypoints = "|".join([f"{p['lat']},{p['lon']}" for p in stops])
    google_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={origin}&waypoints={waypoints}&travelmode=driving"

    st.markdown(f"""
        <a href="{google_url}" target="_blank" style="text-decoration:none;">
            <div style="background:#28a745;color:white;padding:20px;text-align:center;border-radius:15px;font-size:24px;font-weight:bold;">
                🚀 ЗАПУСТИТЬ МАРШРУТ В GOOGLE MAPS
            </div>
        </a>
    """, unsafe_allow_html=True)

    with st.expander("📝 Список остановок по порядку"):
        st.write(f"🚩 **Старт:** {s_name}")
        for i, p in enumerate(stops, 1):
            st.write(f"{i}. {p['name']} " + (f"**(до {p['close']}:00)**" if p['close'] else ""))
        st.write(f"🏁 **Финиш:** Возврат в начало")
