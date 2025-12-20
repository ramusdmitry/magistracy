import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import time

# Настройка страницы
st.set_page_config(
    page_title="🌡️ Анализ температуры",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Кастомные стили
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1E88E5;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .anomaly-hot {
        background-color: #ff4444;
        padding: 10px;
        border-radius: 5px;
        color: white;
    }
    .anomaly-cold {
        background-color: #4444ff;
        padding: 10px;
        border-radius: 5px;
        color: white;
    }
    .normal-temp {
        background-color: #44aa44;
        padding: 10px;
        border-radius: 5px;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Сопоставление месяцев с сезонами
MONTH_TO_SEASON = {
    12: "winter", 1: "winter", 2: "winter",
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn"
}

SEASON_NAMES = {
    "winter": "Зима",
    "spring": "Весна", 
    "summer": "Лето",
    "autumn": "Осень"
}

# Функции для анализа данных
def get_current_season():
    """Определить текущий сезон"""
    month = datetime.now().month
    return MONTH_TO_SEASON[month]

@st.cache_data
def analyze_city_data(city_data: pd.DataFrame) -> pd.DataFrame:
    """
    Анализ данных для одного города:
    - Скользящее среднее (окно 30 дней)
    - Скользящее стандартное отклонение
    - Определение аномалий
    """
    city_df = city_data.copy()
    city_df = city_df.sort_values('timestamp')
    
    city_df['rolling_mean'] = city_df['temperature'].rolling(window=30, center=True).mean()
    city_df['rolling_std'] = city_df['temperature'].rolling(window=30, center=True).std()
    
    city_df['lower_bound'] = city_df['rolling_mean'] - 2 * city_df['rolling_std']
    city_df['upper_bound'] = city_df['rolling_mean'] + 2 * city_df['rolling_std']
    city_df['is_anomaly'] = (city_df['temperature'] < city_df['lower_bound']) | \
                            (city_df['temperature'] > city_df['upper_bound'])
    
    return city_df

@st.cache_data
def process_all_cities(df: pd.DataFrame) -> pd.DataFrame:
    """Обработать все города"""
    results = []
    for city in df['city'].unique():
        city_data = df[df['city'] == city].copy()
        analyzed = analyze_city_data(city_data)
        results.append(analyzed)
    return pd.concat(results, ignore_index=True)

@st.cache_data
def calculate_seasonal_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Рассчитать сезонную статистику"""
    stats = df.groupby(['city', 'season']).agg({
        'temperature': ['mean', 'std', 'min', 'max', 'count']
    }).round(2)
    stats.columns = ['mean_temp', 'std_temp', 'min_temp', 'max_temp', 'count']
    stats = stats.reset_index()
    return stats

def check_temperature_anomaly(city: str, current_temp: float, historical_data: pd.DataFrame) -> dict:
    """
    Проверяет, является ли текущая температура аномальной
    """
    season = get_current_season()
    
    city_season_data = historical_data[
        (historical_data['city'] == city) & 
        (historical_data['season'] == season)
    ]
    
    if len(city_season_data) == 0:
        return {
            "is_anomaly": None,
            "message": f"Нет исторических данных для {city} в сезоне {season}"
        }
    
    mean_temp = city_season_data['temperature'].mean()
    std_temp = city_season_data['temperature'].std()
    lower_bound = mean_temp - 2 * std_temp
    upper_bound = mean_temp + 2 * std_temp
    
    is_anomaly = current_temp < lower_bound or current_temp > upper_bound
    
    if current_temp < lower_bound:
        anomaly_type = "холодная"
    elif current_temp > upper_bound:
        anomaly_type = "жаркая"
    else:
        anomaly_type = None
    
    return {
        "city": city,
        "season": season,
        "season_name": SEASON_NAMES[season],
        "current_temp": current_temp,
        "mean_temp": round(mean_temp, 1),
        "std_temp": round(std_temp, 1),
        "lower_bound": round(lower_bound, 1),
        "upper_bound": round(upper_bound, 1),
        "is_anomaly": is_anomaly,
        "anomaly_type": anomaly_type
    }

@st.cache_data(ttl=300)  # Кэш на 5 минут
def get_current_temperature(city: str, api_key: str) -> dict:
    """
    Синхронный запрос к OpenWeatherMap API
    Используем синхронный подход, т.к.:
    1. Для одиночных запросов разница минимальна
    2. Streamlit сам управляет кэшированием
    3. Код проще в поддержке
    """
    base_url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": api_key,
        "units": "metric"
    }
    
    try:
        response = requests.get(base_url, params=params, timeout=10)
        data = response.json()
        
        if response.status_code == 200:
            return {
                "success": True,
                "city": city,
                "temperature": data["main"]["temp"],
                "feels_like": data["main"]["feels_like"],
                "description": data["weather"][0]["description"],
                "humidity": data["main"]["humidity"],
                "pressure": data["main"]["pressure"],
                "wind_speed": data.get("wind", {}).get("speed", 0)
            }
        else:
            return {
                "success": False,
                "city": city,
                "error": data.get("message", "Unknown error"),
                "code": data.get("cod")
            }
    except Exception as e:
        return {
            "success": False,
            "city": city,
            "error": str(e)
        }

def create_temperature_timeseries(city_data: pd.DataFrame, city: str) -> go.Figure:
    """Создать интерактивный график временного ряда температуры"""
    
    fig = go.Figure()
    
    # Основная линия температуры
    fig.add_trace(go.Scatter(
        x=city_data['timestamp'],
        y=city_data['temperature'],
        mode='lines',
        name='Температура',
        line=dict(color='#1f77b4', width=1),
        hovertemplate='%{x}<br>Температура: %{y:.1f}°C<extra></extra>'
    ))
    
    # Скользящее среднее
    fig.add_trace(go.Scatter(
        x=city_data['timestamp'],
        y=city_data['rolling_mean'],
        mode='lines',
        name='Скользящее среднее (30 дней)',
        line=dict(color='#ff7f0e', width=2),
        hovertemplate='%{x}<br>Скользящее среднее: %{y:.1f}°C<extra></extra>'
    ))
    
    # Границы нормы
    fig.add_trace(go.Scatter(
        x=city_data['timestamp'],
        y=city_data['upper_bound'],
        mode='lines',
        name='Верхняя граница (μ + 2σ)',
        line=dict(color='rgba(255,0,0,0.3)', width=1, dash='dash'),
        hoverinfo='skip'
    ))
    
    fig.add_trace(go.Scatter(
        x=city_data['timestamp'],
        y=city_data['lower_bound'],
        mode='lines',
        name='Нижняя граница (μ - 2σ)',
        line=dict(color='rgba(0,0,255,0.3)', width=1, dash='dash'),
        fill='tonexty',
        fillcolor='rgba(0,100,80,0.1)',
        hoverinfo='skip'
    ))
    
    # Аномалии
    anomalies = city_data[city_data['is_anomaly']]
    fig.add_trace(go.Scatter(
        x=anomalies['timestamp'],
        y=anomalies['temperature'],
        mode='markers',
        name='Аномалии',
        marker=dict(color='red', size=6, symbol='circle'),
        hovertemplate='%{x}<br>🔴 Аномалия: %{y:.1f}°C<extra></extra>'
    ))
    
    fig.update_layout(
        title=f'Временной ряд температуры: {city}',
        xaxis_title='Дата',
        yaxis_title='Температура (°C)',
        hovermode='x unified',
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        height=500
    )
    
    return fig

def create_seasonal_profile(city_data: pd.DataFrame, city: str) -> go.Figure:
    """Создать график сезонного профиля"""
    
    seasonal = city_data.groupby('season').agg({
        'temperature': ['mean', 'std', 'min', 'max']
    }).round(2)
    seasonal.columns = ['mean', 'std', 'min', 'max']
    seasonal = seasonal.reset_index()
    
    # Порядок сезонов
    season_order = ['winter', 'spring', 'summer', 'autumn']
    seasonal['season'] = pd.Categorical(seasonal['season'], categories=season_order, ordered=True)
    seasonal = seasonal.sort_values('season')
    seasonal['season_name'] = seasonal['season'].map(SEASON_NAMES)
    
    fig = go.Figure()
    
    # Средняя температура с погрешностью
    fig.add_trace(go.Bar(
        x=seasonal['season_name'],
        y=seasonal['mean'],
        error_y=dict(type='data', array=seasonal['std'] * 2, visible=True),
        name='Средняя температура ± 2σ',
        marker_color=['#4169E1', '#32CD32', '#FFD700', '#FF8C00'],
        hovertemplate='%{x}<br>Средняя: %{y:.1f}°C<br>σ: ±%{error_y.array:.1f}°C<extra></extra>'
    ))
    
    fig.update_layout(
        title=f'Сезонный профиль температуры: {city}',
        xaxis_title='Сезон',
        yaxis_title='Температура (°C)',
        height=400
    )
    
    return fig

def create_anomaly_distribution(city_data: pd.DataFrame, city: str) -> go.Figure:
    """Создать график распределения аномалий по сезонам"""
    
    anomaly_counts = city_data.groupby(['season', 'is_anomaly']).size().unstack(fill_value=0)
    anomaly_counts = anomaly_counts.reset_index()
    
    season_order = ['winter', 'spring', 'summer', 'autumn']
    anomaly_counts['season'] = pd.Categorical(anomaly_counts['season'], categories=season_order, ordered=True)
    anomaly_counts = anomaly_counts.sort_values('season')
    anomaly_counts['season_name'] = anomaly_counts['season'].map(SEASON_NAMES)
    
    fig = go.Figure(data=[
        go.Bar(name='Норма', x=anomaly_counts['season_name'], 
               y=anomaly_counts[False] if False in anomaly_counts.columns else [0]*len(anomaly_counts),
               marker_color='#44aa44'),
        go.Bar(name='Аномалии', x=anomaly_counts['season_name'], 
               y=anomaly_counts[True] if True in anomaly_counts.columns else [0]*len(anomaly_counts),
               marker_color='#ff4444')
    ])
    
    fig.update_layout(
        title=f'Распределение аномалий по сезонам: {city}',
        xaxis_title='Сезон',
        yaxis_title='Количество дней',
        barmode='stack',
        height=400
    )
    
    return fig

def create_temperature_histogram(city_data: pd.DataFrame, city: str) -> go.Figure:
    """Создать гистограмму распределения температуры"""
    
    fig = px.histogram(
        city_data, 
        x='temperature', 
        color='season',
        nbins=50,
        color_discrete_map={
            'winter': '#4169E1',
            'spring': '#32CD32', 
            'summer': '#FFD700',
            'autumn': '#FF8C00'
        },
        labels={'temperature': 'Температура (°C)', 'season': 'Сезон', 'count': 'Количество'},
        title=f'Распределение температуры по сезонам: {city}'
    )
    
    # Обновляем названия в легенде
    fig.for_each_trace(lambda t: t.update(name=SEASON_NAMES.get(t.name, t.name)))
    
    fig.update_layout(height=400)
    
    return fig


def main():
    st.markdown('<h1 class="main-header">Анализ температурных данных</h1>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("⚙️ Настройки")
        
        st.subheader("📁 Загрузка данных")
        uploaded_file = st.file_uploader(
            "Загрузите CSV файл с историческими данными",
            type=['csv'],
            help="Файл должен содержать колонки: city, timestamp, temperature, season"
        )
        
        st.subheader("🔑 OpenWeatherMap API")
        api_key = st.text_input(
            "API ключ",
            type="password",
            help="Получите ключ на openweathermap.org/api"
        )
        
        if api_key:
            st.success("✅ API ключ введен")
        else:
            st.info("ℹ️ Введите API ключ для получения текущей погоды")
    
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file, parse_dates=['timestamp'])
            st.success(f"✅ Загружено {len(df):,} записей")
        except Exception as e:
            st.error(f"❌ Ошибка загрузки файла: {e}")
            return
    else:
        st.info("👆 Загрузите файл с историческими данными в боковой панели")
        
        if st.button("🎲 Сгенерировать демо-данные"):
            with st.spinner("Генерация данных..."):
                df = generate_demo_data()
                st.session_state['demo_data'] = df
                st.success(f"✅ Сгенерировано {len(df):,} записей")
        
        if 'demo_data' in st.session_state:
            df = st.session_state['demo_data']
        else:
            return
    
    with st.spinner("Анализ данных..."):
        df_analyzed = process_all_cities(df)
        seasonal_stats = calculate_seasonal_stats(df_analyzed)
    
    cities = sorted(df['city'].unique())
    
    col1, col2 = st.columns([2, 1])
    with col1:
        selected_city = st.selectbox(
            "🏙️ Выберите город",
            cities,
            index=0
        )
    with col2:
        current_season = get_current_season()
        st.info(f"📅 Текущий сезон: **{SEASON_NAMES[current_season]}**")
    
    city_data = df_analyzed[df_analyzed['city'] == selected_city]
    city_stats = seasonal_stats[seasonal_stats['city'] == selected_city]
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Статистика", 
        "📈 Временной ряд", 
        "🌤️ Сезонный анализ",
        "🌡️ Текущая погода"
    ])
    
    # Таб 1: Описательная статистика
    with tab1:
        st.subheader(f"📊 Описательная статистика для {selected_city}")
        
        # Метрики
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(
                "Всего записей",
                f"{len(city_data):,}"
            )
        with col2:
            st.metric(
                "Средняя температура",
                f"{city_data['temperature'].mean():.1f}°C"
            )
        with col3:
            st.metric(
                "Мин / Макс",
                f"{city_data['temperature'].min():.1f}°C / {city_data['temperature'].max():.1f}°C"
            )
        with col4:
            anomaly_count = city_data['is_anomaly'].sum()
            anomaly_pct = (anomaly_count / len(city_data)) * 100
            st.metric(
                "Аномалий",
                f"{anomaly_count} ({anomaly_pct:.1f}%)"
            )
        
        # Таблица сезонной статистики
        st.subheader("📋 Статистика по сезонам")
        
        display_stats = city_stats.copy()
        display_stats['season'] = display_stats['season'].map(SEASON_NAMES)
        display_stats.columns = ['Город', 'Сезон', 'Средняя (°C)', 'Ст.откл. (°C)', 'Мин (°C)', 'Макс (°C)', 'Дней']
        
        st.dataframe(
            display_stats[['Сезон', 'Средняя (°C)', 'Ст.откл. (°C)', 'Мин (°C)', 'Макс (°C)', 'Дней']],
            use_container_width=True,
            hide_index=True
        )
        
        # Гистограмма
        st.plotly_chart(
            create_temperature_histogram(city_data, selected_city),
            use_container_width=True
        )
    
    # Таб 2: Временной ряд
    with tab2:
        st.subheader(f"📈 Временной ряд температуры: {selected_city}")
        
        # Фильтр по годам
        years = sorted(city_data['timestamp'].dt.year.unique())
        selected_years = st.slider(
            "Выберите период",
            min_value=int(min(years)),
            max_value=int(max(years)),
            value=(int(min(years)), int(max(years)))
        )
        
        filtered_data = city_data[
            (city_data['timestamp'].dt.year >= selected_years[0]) &
            (city_data['timestamp'].dt.year <= selected_years[1])
        ]
        
        st.plotly_chart(
            create_temperature_timeseries(filtered_data, selected_city),
            use_container_width=True
        )
        
        # Информация об аномалиях
        anomalies_in_period = filtered_data[filtered_data['is_anomaly']]
        if len(anomalies_in_period) > 0:
            with st.expander(f"🔴 Показать аномалии ({len(anomalies_in_period)} записей)"):
                anomaly_display = anomalies_in_period[['timestamp', 'temperature', 'rolling_mean', 'lower_bound', 'upper_bound']].copy()
                anomaly_display.columns = ['Дата', 'Температура', 'Скользящее среднее', 'Нижняя граница', 'Верхняя граница']
                st.dataframe(anomaly_display.round(1), use_container_width=True, hide_index=True)
    
    # Таб 3: Сезонный анализ
    with tab3:
        st.subheader(f"🌤️ Сезонный анализ: {selected_city}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.plotly_chart(
                create_seasonal_profile(city_data, selected_city),
                use_container_width=True
            )
        
        with col2:
            st.plotly_chart(
                create_anomaly_distribution(city_data, selected_city),
                use_container_width=True
            )
        
        # Тренд по годам
        st.subheader("📉 Долгосрочный тренд температуры")
        
        yearly_avg = city_data.groupby(city_data['timestamp'].dt.year)['temperature'].mean().reset_index()
        yearly_avg.columns = ['Год', 'Средняя температура']
        
        fig_trend = px.line(
            yearly_avg,
            x='Год',
            y='Средняя температура',
            title=f'Среднегодовая температура: {selected_city}',
            markers=True
        )
        
        # Добавляем линию тренда
        z = np.polyfit(yearly_avg['Год'], yearly_avg['Средняя температура'], 1)
        p = np.poly1d(z)
        fig_trend.add_trace(go.Scatter(
            x=yearly_avg['Год'],
            y=p(yearly_avg['Год']),
            mode='lines',
            name='Тренд',
            line=dict(dash='dash', color='red')
        ))
        
        st.plotly_chart(fig_trend, use_container_width=True)
        
        trend_direction = "↗️ повышение" if z[0] > 0 else "↘️ понижение"
        st.info(f"📈 Тренд: {trend_direction} ({z[0]:.3f}°C/год)")
    
    # Таб 4: Текущая погода
    with tab4:
        st.subheader(f"🌡️ Текущая погода: {selected_city}")
        
        if not api_key:
            st.warning("⚠️ Введите API ключ OpenWeatherMap в боковой панели для получения текущей погоды")
        else:
            with st.spinner("Загрузка данных о погоде..."):
                weather_data = get_current_temperature(selected_city, api_key)
            
            if weather_data["success"]:
                # Проверка аномальности
                anomaly_check = check_temperature_anomaly(
                    selected_city, 
                    weather_data["temperature"], 
                    df_analyzed
                )
                
                # Отображение текущей погоды
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric(
                        "🌡️ Температура",
                        f"{weather_data['temperature']:.1f}°C",
                        delta=f"Ощущается как {weather_data['feels_like']:.1f}°C"
                    )
                
                with col2:
                    st.metric(
                        "💧 Влажность",
                        f"{weather_data['humidity']}%"
                    )
                
                with col3:
                    st.metric(
                        "💨 Ветер",
                        f"{weather_data['wind_speed']} м/с"
                    )
                
                st.caption(f"☁️ {weather_data['description'].capitalize()}")
                
                # Статус аномальности
                st.divider()
                st.subheader("🔍 Анализ аномальности")
                
                if anomaly_check["is_anomaly"] is not None:
                    col1, col2 = st.columns([1, 2])
                    
                    with col1:
                        if anomaly_check["is_anomaly"]:
                            if anomaly_check["anomaly_type"] == "жаркая":
                                st.error(f"🔴 **АНОМАЛИЯ: Слишком жарко!**")
                            else:
                                st.error(f"🔵 **АНОМАЛИЯ: Слишком холодно!**")
                        else:
                            st.success("🟢 **Температура в норме**")
                    
                    with col2:
                        st.info(f"""
                        **Текущий сезон:** {anomaly_check['season_name']}
                        
                        **Текущая температура:** {anomaly_check['current_temp']:.1f}°C
                        
                        **Историческая норма:** {anomaly_check['lower_bound']}°C — {anomaly_check['upper_bound']}°C
                        
                        **Среднее для сезона:** {anomaly_check['mean_temp']}°C (σ = {anomaly_check['std_temp']}°C)
                        """)
                    
                    # Визуализация
                    fig = go.Figure()
                    
                    fig.add_trace(go.Bar(
                        x=['Диапазон нормы'],
                        y=[anomaly_check['upper_bound'] - anomaly_check['lower_bound']],
                        base=[anomaly_check['lower_bound']],
                        name='Норма',
                        marker_color='rgba(0,200,0,0.3)',
                        width=0.5
                    ))
                    
                    fig.add_trace(go.Scatter(
                        x=['Диапазон нормы'],
                        y=[anomaly_check['current_temp']],
                        mode='markers',
                        name='Текущая температура',
                        marker=dict(
                            size=20,
                            color='red' if anomaly_check['is_anomaly'] else 'green',
                            symbol='diamond'
                        )
                    ))
                    
                    fig.add_hline(
                        y=anomaly_check['mean_temp'],
                        line_dash="dash",
                        annotation_text=f"Среднее: {anomaly_check['mean_temp']}°C"
                    )
                    
                    fig.update_layout(
                        title='Сравнение текущей температуры с нормой',
                        yaxis_title='Температура (°C)',
                        showlegend=True,
                        height=400
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning(anomaly_check["message"])
            
            else:
                # Обработка ошибок API
                if weather_data.get("code") == 401 or weather_data.get("code") == "401":
                    st.error("""
                    ❌ **Ошибка авторизации API**
                    
                    Неверный API ключ. Пожалуйста, проверьте:
                    1. Правильность введенного ключа
                    2. Активирован ли ключ (может занять 2-3 часа после регистрации)
                    
                    [Подробнее об ошибке](https://openweathermap.org/faq#error401)
                    """)
                else:
                    st.error(f"❌ Ошибка получения данных: {weather_data.get('error', 'Неизвестная ошибка')}")

def generate_demo_data():
    """Генерация демо-данных"""
    seasonal_temperatures = {
        "New York": {"winter": 0, "spring": 10, "summer": 25, "autumn": 15},
        "London": {"winter": 5, "spring": 11, "summer": 18, "autumn": 12},
        "Paris": {"winter": 4, "spring": 12, "summer": 20, "autumn": 13},
        "Tokyo": {"winter": 6, "spring": 15, "summer": 27, "autumn": 18},
        "Moscow": {"winter": -10, "spring": 5, "summer": 18, "autumn": 8},
        "Sydney": {"winter": 12, "spring": 18, "summer": 25, "autumn": 20},
        "Berlin": {"winter": 0, "spring": 10, "summer": 20, "autumn": 11},
        "Beijing": {"winter": -2, "spring": 13, "summer": 27, "autumn": 16},
        "Rio de Janeiro": {"winter": 20, "spring": 25, "summer": 30, "autumn": 25},
        "Dubai": {"winter": 20, "spring": 30, "summer": 40, "autumn": 30},
        "Los Angeles": {"winter": 15, "spring": 18, "summer": 25, "autumn": 20},
        "Singapore": {"winter": 27, "spring": 28, "summer": 28, "autumn": 27},
        "Mumbai": {"winter": 25, "spring": 30, "summer": 35, "autumn": 30},
        "Cairo": {"winter": 15, "spring": 25, "summer": 35, "autumn": 25},
        "Mexico City": {"winter": 12, "spring": 18, "summer": 20, "autumn": 15},
    }
    
    dates = pd.date_range(start="2010-01-01", periods=365 * 10, freq="D")
    data = []
    
    for city in seasonal_temperatures:
        for date in dates:
            season = MONTH_TO_SEASON[date.month]
            mean_temp = seasonal_temperatures[city][season]
            temperature = np.random.normal(loc=mean_temp, scale=5)
            data.append({
                "city": city, 
                "timestamp": date, 
                "temperature": temperature,
                "season": season
            })
    
    return pd.DataFrame(data)

if __name__ == "__main__":
    main()

