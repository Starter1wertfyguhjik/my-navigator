import streamlit as st
import folium
from streamlit_folium import st_folium
from geopy.distance import geodesic
import requests
from datetime import datetime, timedelta
import pytz
from streamlit_searchbox import st_searchbox
import time

st.set_page_config(page_title="Smart Navigator MSK", layout="wide")

if "points_list" not in st.session_state:
    st.session_state.points_list = []
if "route_data" not in st.session_state:
    st.session_state.route_data = None

st.title("🚗 Умный Навигатор (Режим работы + Дороги)")

# ---------------- ФУНКЦИЯ ПОИСКА (PHOTON + DEBOUNCE) ----------------
def address_search_provider(search_term: str):
    if not search_term or len(search_term) < 3:
        return []
    
    # Микропауза, чтобы не спамить API при быстром наборе текста
    time.sleep(0.4)
    
    url = "https://photon.komoot.io/api/"
    params = {"q": search_term, "limit": 7, "lang": "ru"}
    
    try:
        r = requests.get(url, params=params, timeout=5)
        if r.status_code == 200:
            features = r.json().get("features", [])
            results = []
            
            for f in features:
                p = f.get("properties", {})
                c = f.get("geometry", {}).get("coordinates") # В Photon это [lon, lat]
                
                # Собираем красивое название для списка
                name_parts = [p.get("city"), p.get("street"), p.get("housenumber"), p.get("name")]
                # Убираем пустые значения и склеиваем
                display_name = ", ".join([str(x) for x in name_parts if x])
                
                if not display_name:
                    display_name = "Неизвестное место"
                    
                # st_searchbox понимает формат кортежа: (То_что_видит_юзер, То_что_вернется_в_код)
                # Возвращаем сразу готовый словарь с координатами!
                results.append((display_name, {"lat": c[1], "lon": c[0], "name": display_name}))
                
            return results
    except Exception as e:
        pass
    
    return []

# ---------------- ЗАПРОС РЕАЛЬНЫХ ДОРОГ (OSRM) ----------------
def get_osrm_route(start_coords, end_coords):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}?overview=false"
    try:
        r = requests.get(url, timeout=3)
        data = r.json()
        if data.get("code") == "Ok":
            dist_km = data["routes"][0]["distance"] / 1000.0
            duration_sec = data["routes"][0]["duration"]
            return dist_km, duration_sec / 3600.0
    except Exception:
        pass
    
    dist_km = geodesic(start_coords, end_coords).km
    return dist_km, dist_km / 30.0

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.header("📍 Настройка маршрута")

    st.write("**Откуда едем?**")
    # start_addr теперь содержит не строку, а словарь с координатами!
    start_addr = st_searchbox(
        address_search_provider,
        key="start_search",
        placeholder="Начните вводить адрес старта..."
    )

    st.markdown("---")
    
    st.write("**Добавить точку назначения:**")
    new_point_addr = st_searchbox(
        address_search_provider,
        key="point_search",
        placeholder="Поиск адреса точки..."
    )
    
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
                # Берем готовые данные прямо из поисковой строки
                st.session_state.points_list.append({
                    "lat": new_point_addr["lat"],
                    "lon": new_point_addr["lon"],
                    "name": new_point_addr["name"], 
                    "open": open_h, 
                    "close": close_h
                })
                st.toast(f"Добавлено: {new_point_addr['name']}")
        else:
            st.warning("Выберите адрес из выпадающего списка!")

    if st.session_state.points_list:
        st.write("**Ваш список:**")
        for i, p in enumerate(st.session_state.points_list):
            st.caption(f"{i+1}. {p['name'][:30]}... ({p['open']}:00 - {p['close']}:00)")
        
        if st.button("🗑 Очистить все"):
            st.session_state.points_list = []
            st.session_state.route_data = None
            st.rerun()

    st.markdown("---")
    btn_calc = st.button("🚀 ПОСТРОИТЬ МАРШРУТ", use_container_width=True)

# ---------------- УМНАЯ ОПТИМИЗАЦИЯ ----------------
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
            dist, travel_hours = get_osrm_route(current_pos, (p["lat"], p["lon"]))
            arrival_time = current_time + timedelta(hours=travel_hours)
            
            open_time = arrival_time.replace(hour=p["open"], minute=0, second=0)
            close_time = arrival_time.replace(hour=p["close"], minute=0, second=0)
            
            score = travel_hours * 60 
            
            if arrival_time > close_time:
                score += 10000 
            elif arrival_time < open_time:
                wait_minutes = (open_time - arrival_time).total_seconds() / 60
                score += wait_minutes * 0.5  
            else:
                minutes_to_close = (close_time - arrival_time).total_seconds() / 60
                if minutes_to_close < 60:
                    score -= (60 - minutes_to_close) 
            
            if score < min_score:
                min_score = score
                best = p
                best_travel_time = travel_hours

        chosen = best
        current_time += timedelta(hours=best_travel_time)
        
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
            # Координаты старта уже есть в start_addr
            start_coords = (start_addr["lat"], start_addr["lon"])
            start_name = start_addr["name"]
            
            # Точки тоже уже с координатами, просто отдаем их в функцию
            ordered, msk_time = optimize_route(start_coords, st.session_state.points_list)
            
            st.session_state.route_data = {
                "start": (start_coords[0], start_coords[1], start_name), 
                "stops": ordered, 
                "msk_start_time": msk_time
            }

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
