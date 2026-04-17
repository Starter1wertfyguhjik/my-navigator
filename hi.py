import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
from datetime import datetime, timedelta
import pytz
from streamlit_searchbox import st_searchbox
import time

# 1. Настройка страницы
st.set_page_config(page_title="Smart Navigator", layout="wide")

# 2. Инициализация переменных в сессии
if "points_list" not in st.session_state:
    st.session_state.points_list = []
if "route_data" not in st.session_state:
    st.session_state.route_data = None

st.title("🚗 Умный Навигатор")

# 3. ФУНКЦИЯ ПОИСКА (Photon API)
@st.cache_data(ttl=600)
def address_search_provider(search_term: str):
    if not search_term or len(search_term) < 3:
        return []
    
    url = "https://photon.komoot.io/api/"
    params = {"q": search_term, "limit": 10, "lang": "ru"}
    
    try:
        # Убираем задержку или делаем её минимальной
        r = requests.get(url, params=params, timeout=5)
        if r.status_code == 200:
            features = r.json().get("features", [])
            results = []
            for f in features:
                p = f.get("properties", {})
                coords = f.get("geometry", {}).get("coordinates") # [lon, lat]
                
                # Формируем имя: Город, Улица, Номер дома
                name_parts = [p.get("city"), p.get("street"), p.get("housenumber")]
                display_name = ", ".join([str(x) for x in name_parts if x])
                if not display_name:
                    display_name = p.get("name", "Неизвестное место")
                
                # Добавляем в список (Текст для выбора, Объект с данными)
                results.append((display_name, {
                    "lat": coords[1], 
                    "lon": coords[0], 
                    "name": display_name
                }))
            return results
    except Exception as e:
        print(f"Ошибка поиска: {e}")
    return []

# 4. ЗАПРОС ДОРОГ (OSRM)
def get_osrm_route(start_coords, end_coords):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}?overview=false"
    try:
        r = requests.get(url, timeout=3)
        data = r.json()
        if data.get("code") == "Ok":
            route = data["routes"][0]
            return route["distance"] / 1000.0, route["duration"] / 3600.0
    except:
        pass
    return 0, 0.5

# 5. ОПТИМИЗАЦИЯ
def optimize_route(start_coords, points):
    tz = pytz.timezone('Europe/Moscow')
    curr_time = datetime.now(tz)
    curr_pos = (start_coords[0], start_coords[1])
    ordered = []
    temp = points[:]

    while temp:
        best_p, min_score, travel_h = None, float('inf'), 0
        for p in temp:
            dist, h = get_osrm_route(curr_pos, (p["lat"], p["lon"]))
            arr_time = curr_time + timedelta(hours=h)
            
            score = h * 60
            if arr_time.hour >= p["close"]: score += 10000 
            elif arr_time.hour < p["open"]: score += (p["open"] - arr_time.hour) * 20
            
            if score < min_score:
                min_score, best_p, travel_h = score, p, h
        
        curr_time += timedelta(hours=travel_h)
        if curr_time.hour < best_p["open"]:
            curr_time = curr_time.replace(hour=best_p["open"], minute=0)
            
        curr_pos = (best_p["lat"], best_p["lon"])
        ordered.append(best_p)
        temp.remove(best_p)
    return ordered, datetime.now(tz).strftime("%H:%M")

# 6. БОКОВАЯ ПАНЕЛЬ
with st.sidebar:
    st.header("⚙️ Настройки")
    
    st.write("**Откуда едем?**")
    start_point = st_searchbox(address_search_provider, key="start_box")

    st.markdown("---")
    st.write("**Добавить точку:**")
    new_point = st_searchbox(address_search_provider, key="dest_box")
    
    c1, c2 = st.columns(2)
    with c1: open_h = st.number_input("Откр.", 0, 23, 9)
    with c2: close_h = st.number_input("Закр.", 0, 23, 21)
    
    if st.button("➕ Добавить"):
        if new_point:
            st.session_state.points_list.append({
                "lat": new_point["lat"], "lon": new_point["lon"],
                "addr": new_point["name"], "open": open_h, "close": close_h
            })
            st.rerun()

    if st.session_state.points_list:
        st.write("---")
        for i, p in enumerate(st.session_state.points_list):
            st.caption(f"{i+1}. {p['addr']}")
        if st.button("🗑 Очистить"):
            st.session_state.points_list = []
            st.rerun()

    btn_calc = st.button("🚀 ПОСТРОИТЬ", use_container_width=True)

# 7. ГЛАВНЫЙ ЭКРАН
if btn_calc:
    if start_point and st.session_state.points_list:
        with st.spinner("Считаем маршрут..."):
            ordered, msk_t = optimize_route((start_point["lat"], start_point["lon"]), st.session_state.points_list)
            st.session_state.route_data = {"start": start_point, "stops": ordered, "time": msk_t}
    else:
        st.warning("Выберите старт и добавьте точки!")

if st.session_state.route_data:
    rd = st.session_state.route_data
    
    m = folium.Map(location=[rd['start']['lat'], rd['start']['lon']], zoom_start=11)
    folium.Marker([rd['start']['lat'], rd['start']['lon']], icon=folium.Icon(color='red')).add_to(m)
    
    path = [[rd['start']['lat'], rd['start']['lon']]]
    for i, p in enumerate(rd['stops'], 1):
        folium.Marker([p['lat'], p['lon']], tooltip=p['addr'], icon=folium.Icon(color='blue')).add_to(m)
        path.append([p['lat'], p['lon']])
    
    path.append([rd['start']['lat'], rd['start']['lon']])
    folium.PolyLine(path, color="blue", weight=3).add_to(m)
    
    st_folium(m, width="100%", height=500, key="main_map")

    # Ссылка Google Maps
    wp = "|".join([f"{p['lat']},{p['lon']}" for p in rd['stops']])
    g_url = f"https://www.google.com/maps/dir/?api=1&origin={rd['start']['lat']},{rd['start']['lon']}&destination={rd['start']['lat']},{rd['start']['lon']}&waypoints={wp}&travelmode=driving"

    st.markdown(f'<a href="{g_url}" target="_blank"><div style="background:#28a745;color:white;padding:15px;text-align:center;border-radius:10px;font-weight:bold;">ОТКРЫТЬ В GOOGLE MAPS</div></a>', unsafe_allow_html=True)
