import streamlit as st
import requests
from streamlit_searchbox import st_searchbox
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Test Search")

# Функция поиска (упрощенная)
def search_provider(search_term: str):
    if len(search_term) < 3: return []
    url = f"https://photon.komoot.io/api/?q={search_term}&limit=5&lang=ru"
    try:
        r = requests.get(url, timeout=5)
        features = r.json().get("features", [])
        return [(f["properties"].get("name", "Место"), f["geometry"]["coordinates"]) for f in features]
    except:
        return []

st.title("Проверка поиска")

# Поиск
selected_value = st_searchbox(search_provider, key="test_search")

if selected_value:
    lon, lat = selected_value
    st.success(f"Выбрано: {lat}, {lon}")
    
    # Карта
    m = folium.Map(location=[lat, lon], zoom_start=15)
    folium.Marker([lat, lon]).add_to(m)
    st_folium(m, height=300, width=700)
else:
    st.info("Введите хотя бы 3 буквы города или улицы в поле поиска")
