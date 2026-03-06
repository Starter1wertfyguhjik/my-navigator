import streamlit as st
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import requests
from datetime import datetime, timedelta

# Настройка страницы
st.set_page_config(page_title="Smart Navigator 2026", layout="wide")

if "route_data" not in st.session_state:
    st.session_state.route_data = None

st.title("🚗 Умный Навигатор: Оптимизация по времени")

# ---------------- ФУНКЦИИ ГЕОКОДИРОВАНИЯ ----------------
def address_search(query):
    """Поиск подсказок адресов"""
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": query, "format": "json", "limit": 5}
    try:
        r = requests.get(url, params=params)
        return [x["display_name"] for x in r.json()]
    except:
        return []

@st.cache_data
def get_coordinates_cached(address):
    """Превращает адрес в координаты с кэшированием"""
    try:
        geolocator = Nominatim(user_agent="smart_nav_pro_2026")
        loc = geolocator.geocode(address, timeout=10)
        if loc:
            return loc.latitude, loc.longitude, loc.address
    except:
        pass
    return None

# ---------------- ЛОГИКА ОПТИМИЗАЦИИ ----------------
def optimize_route_by_time(start_coords, points):
    """Выбирает путь на основе близости и времени закрытия"""
    avg_speed = 30  # км/ч (городской трафик)
    current_time = datetime.now()
    current_pos = start_coords
    ordered_route = []
    remaining_points = points[:]

    while remaining_points:
        best_pt = None
        min_score = float('inf')

        for p in remaining_points:
            dist = geodesic(current_pos, (p["lat"], p["lon"])).km
            travel_hours = dist / avg_speed
            arrival_time = current_time + timedelta(hours=travel_hours)

            # Расчет приоритета (Score)
            if p["close"]:
                # Создаем объект времени закрытия для сегодня
                close_dt = current_time.replace(hour=p["close"], minute=0, second=0, microsecond=0)
                
                # Если точка уже закрыта или закроется вот-вот
                hours_left = (close_dt - arrival_time).total_seconds() / 3600
                
                if hours_left < 0:
                    # Опоздали — ставим в самый конец (огромный score)
                    score = 1000 + dist
                else:
                    # Чем меньше времени до закрытия, тем меньше score (выше приоритет)
                    # Формула учитывает и расстояние, и срочность
                    score = dist + (hours_left * 10)
            else:
                # Точки без дедлайна имеют средний приоритет
                score = dist + 100 

            if score < min_score:
                min_score = score
                best_pt = p

        # Фиксируем выбор
        target = best_pt if best_pt else remaining_points[0]
        step_dist = geodesic(current_pos, (target["lat"], target["lon"])).km
        
        # Обновляем "виртуальное" время и позицию
        current_time += timedelta(hours=step_dist / avg_speed)
        current_pos = (target["lat"], target["lon"])
        ordered_route.append(target)
        remaining_points.remove(target)

    return ordered_route

# ---------------- ИНТЕРФЕЙС (SIDEBAR) ----------------
with st.sidebar:
    st.header("📍 Настройка пути")
    start_query = st.text_input("Откуда едем?", "Москва, Красная площадь")
    
    # Парсинг точек
    dest_raw = st.text_area(
        "Список точек (Адрес | Час закрытия)",
        "Москва, Тверская 1 | 18\nМосква, Новый Арбат 10 | 22\nМосква, ВДНХ",
        height=150
    )
    
    btn_calc = st.button("🚀 Рассчитать маршрут")
    st.info("Пример: 'Адрес | 18' — точка закроется в 18:00")

# ---------------- ОБРАБОТКА НАЖАТИЯ ----------------
if btn_calc:
    with st.spinner("Анализируем пробки и графики работы..."):
        start_data = get_coordinates_cached(start_query)
        if start_data:
            # Парсим текстовое поле
            raw_lines = [line.strip() for line in dest_raw.split("\n") if line.strip()]
            parsed_points = []
            
            for line in raw_lines:
                if "|" in line:
                    parts = line.split("|")
                    addr, close_h = parts[0].strip(), int(parts[1].strip())
                else:
                    addr, close_h = line.strip(), None
                
                coords = get_coordinates_cached(addr)
                if coords:
                    parsed_points.append({
                        "lat": coords[0], "lon": coords[1], 
                        "name": coords[2], "close": close_h
                    })

            # Оптимизируем
            if parsed_points:
                final_stops = optimize_route_by_time((start_data[0], start_data[1]), parsed_points)
                st.session_state.route_data = {
                    "start": start_data,
                    "stops": final_stops
                }
            else:
                st.error("Не удалось распознать адреса точек!")
        else:
            st.error("Начальный адрес не найден.")

# ---------------- ВЫВОД РЕЗУЛЬТАТОВ ----------------
if st.session_state.route_data:
    res = st.session_state.route_data
    s_lat, s_lon, s_name = res["start"]
    stops = res["stops"]

    # Линия маршрута
    path_coords = [(s_lat, s_lon)] + [(p["lat"], p["lon"]) for p in stops] + [(s_lat, s_lon)]

    # Карта (Исправленная, чтобы не белела)
    m = folium.Map(location=[s_lat, s_lon], zoom_start=12)
    folium.PolyLine(path_coords, color="#3498db", weight=5, opacity=0.8).add_to(m)

    # Маркеры
    folium.Marker([s_lat, s_lon], tooltip="СТАРТ", icon=folium.Icon(color="red", icon="home")).add_to(m)
    for i, p in enumerate(stops, 1):
        popup_text = f"{i}. {p['name']}"
        if p['close']: popup_text += f" (До {p['close']}:00)"
        folium.Marker([p["lat"], p["lon"]], tooltip=popup_text, icon=folium.Icon(color="blue")).add_to(m)

    # ВАЖНО: returned_objects=[] лечит "белый экран" при движении мыши
    st_folium(m, width="100%", height=500, returned_objects=[], key="map_display")

    # Кнопка для телефона
    origin_str = f"{s_lat},{s_lon}"
    waypts_str = "|".join([f"{p['lat']},{p['lon']}" for p in stops])
    # Прямая команда для GPS-приложения
    nav_url = f"https://www.google.com/maps/dir/?api=1&origin={origin_str}&destination={origin_str}&waypoints={waypts_str}&travelmode=driving"

    st.markdown(f"""
        <a href="{nav_url}" target="_blank" style="text-decoration:none;">
            <div style="background:#28a745; color:white; padding:20px; text-align:center; border-radius:15px; font-size:22px; font-weight:bold; box-shadow: 0 4px 8px rgba(0,0,0,0.2);">
                🚀 ОТКРЫТЬ В НАВИГАТОРЕ
            </div>
        </a>
    """, unsafe_allow_html=True)

    with st.expander("📝 Детальный план (по порядку срочности)"):
        st.write(f"🚩 **Старт:** {s_name}")
        for i, p in enumerate(stops, 1):
            time_info = f" — ⚠️ До {p['close']}:00" if p['close'] else ""
            st.write(f"{i}. {p['name']}{time_info}")
        st.write(f"🏁 **Финиш:** Возврат на базу")

