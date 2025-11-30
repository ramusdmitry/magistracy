import pandas as pd
import numpy as np
import pickle
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler, OneHotEncoder

df_train = pd.read_csv('https://raw.githubusercontent.com/Murcha1990/MLDS_ML_2022/main/Hometasks/HT1/cars_train.csv')

# Предобработка
def preprocess_column(df, col):
    df[col] = df[col].astype(str).str.extract(r'([\d.]+)').astype(float)
    return df

for col in ['mileage', 'engine', 'max_power']:
    df_train = preprocess_column(df_train, col)

numeric_cols = ['year', 'km_driven', 'mileage', 'engine', 'max_power', 'seats']
for col in numeric_cols:
    df_train[col] = df_train[col].fillna(df_train[col].median())

df_train = df_train.drop(columns=['name', 'torque'])
df_train = df_train.dropna()

y_train = df_train['selling_price']
X_train = df_train.drop(columns=['selling_price'])

categorical_features = ['fuel', 'seller_type', 'transmission', 'owner']
numeric_features = ['year', 'km_driven', 'mileage', 'engine', 'max_power', 'seats']

X_train_numeric = X_train[numeric_features].copy()
X_train_categorical = X_train[categorical_features].copy()

ohe = OneHotEncoder(drop='first', sparse_output=False, handle_unknown='ignore')
X_train_ohe = ohe.fit_transform(X_train_categorical)

X_train_final = np.hstack([X_train_numeric.values, X_train_ohe])

scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train_final)

model = Ridge(alpha=100)  # Оптимальный параметр найден через GridSearchCV
model.fit(X_train_scaled, y_train)

feature_names = numeric_features + list(ohe.get_feature_names_out(categorical_features))

with open('model.pkl', 'wb') as f:
    pickle.dump({
        'model': model,
        'scaler': scaler,
        'ohe': ohe,
        'numeric_features': numeric_features,
        'categorical_features': categorical_features,
        'feature_names': feature_names,
        'df_train': df_train
    }, f)

print("Модель сохранена в model.pkl")

