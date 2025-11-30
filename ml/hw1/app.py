import streamlit as st
import pandas as pd
import numpy as np
import pickle
import matplotlib.pyplot as plt
import seaborn as sns

st.set_page_config(page_title="Предсказание цены автомобиля", layout="wide")
st.title("🚗 Предсказание стоимости автомобиля")

@st.cache_resource
def load_model():
    with open('model.pkl', 'rb') as f:
        return pickle.load(f)

try:
    data = load_model()
    model = data['model']
    scaler = data['scaler']
    ohe = data['ohe']
    numeric_features = data['numeric_features']
    categorical_features = data['categorical_features']
    feature_names = data['feature_names']
    df_train = data['df_train']
except:
    st.error("Сначала запустите save_model.py для создания model.pkl")
    st.stop()

tab1, tab2, tab3 = st.tabs(["📊 EDA", "🔮 Предсказание", "⚖️ Веса модели"])

# TAB 1: EDA
with tab1:
    st.header("Exploratory Data Analysis")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Распределение цен")
        fig, ax = plt.subplots(figsize=(8, 5))
        sns.histplot(df_train['selling_price'], bins=50, ax=ax, color='steelblue')
        ax.set_xlabel("Цена")
        ax.set_ylabel("Количество")
        st.pyplot(fig)
        
    with col2:
        st.subheader("Распределение года выпуска")
        fig, ax = plt.subplots(figsize=(8, 5))
        sns.histplot(df_train['year'], bins=30, ax=ax, color='coral')
        ax.set_xlabel("Год")
        ax.set_ylabel("Количество")
        st.pyplot(fig)
    
    col3, col4 = st.columns(2)
    
    with col3:
        st.subheader("Цена vs Мощность")
        fig, ax = plt.subplots(figsize=(8, 5))
        sns.scatterplot(data=df_train, x='max_power', y='selling_price', alpha=0.5, ax=ax)
        ax.set_xlabel("Мощность (bhp)")
        ax.set_ylabel("Цена")
        st.pyplot(fig)
        
    with col4:
        st.subheader("Цена по типу топлива")
        fig, ax = plt.subplots(figsize=(8, 5))
        sns.boxplot(data=df_train, x='fuel', y='selling_price', ax=ax)
        ax.set_xlabel("Тип топлива")
        ax.set_ylabel("Цена")
        st.pyplot(fig)
    
    st.subheader("Корреляционная матрица")
    fig, ax = plt.subplots(figsize=(10, 8))
    corr = df_train[numeric_features + ['selling_price']].corr()
    sns.heatmap(corr, annot=True, fmt='.2f', cmap='coolwarm', center=0, ax=ax)
    st.pyplot(fig)

# TAB 2: Prediction
with tab2:
    st.header("Предсказание цены")
    
    input_method = st.radio("Способ ввода:", ["Ручной ввод", "Загрузить CSV"])
    
    if input_method == "Ручной ввод":
        col1, col2, col3 = st.columns(3)
        
        with col1:
            year = st.number_input("Год выпуска", min_value=1990, max_value=2024, value=2015)
            km_driven = st.number_input("Пробег (км)", min_value=0, max_value=1000000, value=50000)
        
        with col2:
            mileage = st.number_input("Расход (kmpl)", min_value=0.0, max_value=50.0, value=18.0)
            engine = st.number_input("Объем двигателя (CC)", min_value=500, max_value=5000, value=1200)
        
        with col3:
            max_power = st.number_input("Мощность (bhp)", min_value=30.0, max_value=500.0, value=80.0)
            seats = st.selectbox("Количество мест", [2, 4, 5, 6, 7, 8, 9, 10], index=2)
        
        col4, col5 = st.columns(2)
        
        with col4:
            fuel = st.selectbox("Тип топлива", ['Petrol', 'Diesel', 'CNG', 'LPG', 'Electric'])
            seller_type = st.selectbox("Тип продавца", ['Individual', 'Dealer', 'Trustmark Dealer'])
        
        with col5:
            transmission = st.selectbox("Коробка передач", ['Manual', 'Automatic'])
            owner = st.selectbox("Владелец", ['First Owner', 'Second Owner', 'Third Owner', 'Fourth & Above Owner', 'Test Drive Car'])
        
        if st.button("Предсказать цену", type="primary"):
            input_data = pd.DataFrame({
                'year': [year], 'km_driven': [km_driven], 'mileage': [mileage],
                'engine': [engine], 'max_power': [max_power], 'seats': [seats],
                'fuel': [fuel], 'seller_type': [seller_type],
                'transmission': [transmission], 'owner': [owner]
            })
            
            X_num = input_data[numeric_features].values
            X_cat = ohe.transform(input_data[categorical_features])
            X_final = np.hstack([X_num, X_cat])
            X_scaled = scaler.transform(X_final)
            
            prediction = model.predict(X_scaled)[0]
            st.success(f"💰 Предсказанная цена: **{prediction:,.0f}** рупий")
    
    else:
        uploaded_file = st.file_uploader("Загрузите CSV файл", type=['csv'])
        
        if uploaded_file:
            df_input = pd.read_csv(uploaded_file)
            st.write("Загруженные данные:")
            st.dataframe(df_input.head())
            
            if st.button("Предсказать для всех", type="primary"):
                try:
                    X_num = df_input[numeric_features].values
                    X_cat = ohe.transform(df_input[categorical_features])
                    X_final = np.hstack([X_num, X_cat])
                    X_scaled = scaler.transform(X_final)
                    
                    predictions = model.predict(X_scaled)
                    df_input['predicted_price'] = predictions
                    
                    st.write("Результаты:")
                    st.dataframe(df_input)
                    
                    csv = df_input.to_csv(index=False)
                    st.download_button("Скачать результаты", csv, "predictions.csv", "text/csv")
                except Exception as e:
                    st.error(f"Ошибка: {e}")

# TAB 3: Model Weights
with tab3:
    st.header("Веса модели Ridge Regression")
    
    coefficients = pd.DataFrame({
        'Признак': feature_names,
        'Вес': model.coef_
    }).sort_values('Вес', key=abs, ascending=False)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        fig, ax = plt.subplots(figsize=(10, 8))
        colors = ['green' if x > 0 else 'red' for x in coefficients['Вес']]
        bars = ax.barh(coefficients['Признак'], coefficients['Вес'], color=colors)
        ax.set_xlabel('Вес коэффициента')
        ax.set_title('Важность признаков (веса Ridge модели)')
        ax.axvline(x=0, color='black', linewidth=0.5)
        plt.tight_layout()
        st.pyplot(fig)
    
    with col2:
        st.subheader("Таблица весов")
        st.dataframe(coefficients, hide_index=True)
        
        st.metric("Intercept (bias)", f"{model.intercept_:,.2f}")
    
    st.info("🟢 Зелёный = положительное влияние на цену\n🔴 Красный = отрицательное влияние на цену")

