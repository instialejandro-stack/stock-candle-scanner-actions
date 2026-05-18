# Stock Candle Scanner

Scanner local en Python para detectar diariamente las 10 acciones del universo de Trade Republic con las velas japonesas alcistas de mayor cuerpo porcentual, usando datos diarios de Yahoo Finance mediante `yfinance`.

## Que Hace El Scanner

`scanner.py` lee `data/trade_republic_stocks.csv`, descarga las ultimas velas diarias disponibles de cada ticker con `period="10d"` e `interval="1d"`, toma la ultima vela diaria cerrada, filtra solo velas alcistas y genera un top 10 ordenado por `body_pct`.

El sistema puede ejecutarse en local y tambien puede automatizarse con GitHub Actions para enviar el informe por Telegram.

## Vela Alcista

Una vela se considera alcista cuando:

```text
close > open
```

Las velas que no cumplen esa condicion se ignoran.

## Cuerpo Absoluto

El cuerpo absoluto de la vela se calcula como:

```text
body = close - open
```

Este valor mide la subida en unidades de precio.

## Cuerpo Porcentual

El cuerpo porcentual se calcula como:

```text
body_pct = ((close - open) / open) * 100
```

El ranking se ordena por `body_pct` y no por `body` absoluto porque permite comparar acciones con precios muy distintos. Una subida de 5 euros no significa lo mismo en una accion de 20 euros que en una accion de 500 euros.

## CSV De Acciones

Edita `data/trade_republic_stocks.csv` para definir el universo de acciones. Debe incluir como minimo estas columnas:

```csv
ticker,name,isin,market
AAPL,Apple,US0378331005,USA
MSFT,Microsoft,US5949181045,USA
```

Puedes usar tickers compatibles con Yahoo Finance, incluidos sufijos como `MC.PA` o `SAP.DE`. No uses indices como `^GSPC`, `^IXIC` o `^DJI`.

## Ampliar el universo de acciones

El sistema analiza unicamente las acciones presentes en `data/trade_republic_stocks.csv`. Para obtener mejores resultados conviene ampliar ese CSV con muchas mas acciones disponibles en Trade Republic, especialmente acciones liquidas.

Los tickers deben estar en formato compatible con Yahoo Finance. Ejemplos:

- `AAPL` para Apple en Estados Unidos.
- `MSFT` para Microsoft.
- `SAP.DE` para SAP en Alemania.
- `MC.PA` para LVMH en Paris.
- `SAN.MC` para Banco Santander en Espana.

No deben anadirse indices como:

- `^GSPC`
- `^IXIC`
- `^DJI`

Si un ticker falla, el sistema lo ignorara y continuara con el resto. Es recomendable empezar con 50-100 acciones liquidas y luego ampliar el universo progresivamente.

## Instalar Dependencias

Requiere Python 3.11.

```bash
pip install -r requirements.txt
```

## Ejecutar En Local

```bash
python scanner.py
```

Al ejecutarse, el script muestra la hora de ejecucion, el numero de tickers cargados, una tabla Markdown con el top 10 y las rutas de los archivos actualizados.

Flujo local completo:

```bash
pip install -r requirements.txt
python scanner.py
python intraday_analyzer.py
```

## Analizador Intradia

`intraday_analyzer.py` es la segunda fase local. Lee `output/top10_bullish_candles.csv`, que debe generarse primero con `scanner.py`, y clasifica esas acciones como candidatas intradia mediante criterios cuantitativos. No genera recomendaciones directas de compra.

Ejecuta primero:

```bash
python scanner.py
```

Despues ejecuta:

```bash
python intraday_analyzer.py
```

El analizador descarga datos diarios adicionales con `yfinance`, calcula volumen relativo, retornos recientes, ATR, posicion del cierre, cercania a maximos de 20 dias y gap si esta disponible.

En consola muestra una tabla compacta con `rank`, `ticker`, `name`, `body_pct`, `relative_volume`, `return_5d`, `atr_pct`, `score` y `classification`. El CSV y el Markdown conservan la tabla detallada con `notes`.

## Score Intradia

El score intradia va de 0 a 100 y combina:

- Fuerza de la vela previa.
- Volumen relativo frente al volumen medio de 20 sesiones.
- Tendencia reciente de 5, 10 y 20 dias.
- Liquidez por volumen medio.
- Volatilidad mediante ATR.
- Cierre cerca de maximos.
- Cercania a maximos de 20 dias.
- Gap premarket o precio reciente si esta disponible.

Si el gap no esta disponible, el score se normaliza sobre los puntos disponibles para no penalizar injustamente ese dato ausente. Tambien se aplican penalizaciones por sobreextension, como cuerpo demasiado alto, subida reciente excesiva, gap extremo o ATR muy elevado.

## Clasificaciones Intradia

- `Alta prioridad`: score >= 75.
- `Media prioridad`: score >= 60 y < 75.
- `Baja prioridad`: score >= 45 y < 60.
- `Descartar`: score < 45.

Estas clasificaciones indican calidad cuantitativa como candidata intradia, no una orden de compra.

## Regla Obligatoria De Liquidez

Despues de calcular el score se aplica un limite por volumen medio de 20 sesiones:

- Si `avg_volume_20d < 300.000`, la clasificacion maxima es `Baja prioridad`.
- Si `avg_volume_20d >= 300.000` y `< 1.000.000`, la clasificacion maxima es `Media prioridad`.
- Si `avg_volume_20d >= 1.000.000`, no se limita la clasificacion.

Cuando esta regla limita una accion, la columna `notes` lo indica.

## Automatización con GitHub Actions y Telegram

El workflow `.github/workflows/daily-candle-scan.yml` ejecuta el flujo completo de lunes a viernes a las `22:15 UTC`:

```text
15 22 * * 1-5
```

Ese horario queda despues del cierre regular del mercado estadounidense. El workflow tambien se puede ejecutar manualmente desde la pestaña GitHub Actions usando `workflow_dispatch`.

El workflow diario:

1. Hace checkout del repositorio.
2. Instala Python 3.11.
3. Instala dependencias desde `requirements.txt`.
4. Ejecuta `python scanner.py`.
5. Ejecuta `python intraday_analyzer.py`.
6. Hace commit y push de los informes generados si han cambiado.
7. Envia por Telegram un resumen corto construido desde `output/intraday_candidates.csv`.
8. Envia despues el contenido completo de `output/intraday_candidates.md`.

Los archivos que actualiza son:

- `output/top10_bullish_candles.csv`
- `output/history_top10_bullish_candles.csv`
- `output/intraday_candidates.csv`
- `output/intraday_candidates.md`
- `output/history_intraday_candidates.csv`

Si no hay cambios, el workflow muestra `No changes to commit` y continua con el envio a Telegram.

### Configurar Telegram

1. Crea un bot hablando con BotFather en Telegram.
2. Copia el token del bot.
3. Obten tu `chat_id` enviando un mensaje al bot y consultando las actualizaciones del bot, o usando una herramienta de confianza para obtener el ID del chat.
4. En GitHub, abre `Settings` > `Secrets and variables` > `Actions`.
5. Crea estos secretos:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
6. Ejecuta manualmente el workflow desde GitHub Actions para probar el envio.

No incluyas tokens reales en el codigo ni en el README.

Para probar Telegram en local, define las variables de entorno y ejecuta:

```bash
python send_telegram_report.py
```

## Archivos Generados

El script crea automaticamente `output/` si no existe y genera:

- `output/top10_bullish_candles.csv`: resultado actual.
- `output/history_top10_bullish_candles.csv`: historico acumulado.
- `output/intraday_candidates.csv`: candidatas intradia actuales.
- `output/intraday_candidates.md`: informe Markdown de candidatas intradia, con resumen ejecutivo, tabla detallada, `notes` y advertencia de riesgo.
- `output/history_intraday_candidates.csv`: historico de candidatas intradia.

El CSV de salida tiene exactamente estas columnas:

```text
rank,date,ticker,name,isin,market,open,close,high,low,body,body_pct,volume
```

El historico evita duplicados usando la clave:

```text
date,ticker
```

## Limitaciones

- `yfinance` no esta afiliado oficialmente a Yahoo Finance.
- El sistema no consulta directamente Trade Republic.
- El CSV se asume como universo de acciones disponibles en Trade Republic.
- Puede haber retrasos, festivos, sesiones sin datos o datos incompletos.
- Esto no es asesoramiento financiero.
- Las senales no garantizan rentabilidad.
- Las operaciones intradia tienen riesgo elevado.
- No se consultan noticias ni datos fundamentales.
