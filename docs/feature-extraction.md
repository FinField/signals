# Feature-extractie uit vank-tijdseries — handleiding

**Kernregel (scheiding van lagen):**

| Laag | Wat | Waar |
|---|---|---|
| **Vastlegging (p2p)** | Ruwe waarnemingen: exacte waarde, tijdstip, bron, handtekening, CID | vank / FinField-veld, 5mart.ml ↔ knitweb.art |
| **Datapreparatie (ML)** | Normalisaties, momentum, afgeleiden, interacties | Lokaal in de feature-pipeline, berekend uit CID-gepinde series |

Afgeleide grootheden worden **nooit** als feiten het veld in geweven. Ze zijn functies van de ruwe series en dus altijd reproduceerbaar: `features = f(raw_series, code_versie)`. Wie de ruwe series en de feature-code heeft, kan elke feature exact herberekenen — ook zonder internet.

## 0. Notatie en voorbereiding

Een serie is `x_t` met waarnemingen op tijdstippen `t` (dagelijks voor prijzen, maandelijks voor macro). Vóór alles:

- **Point-in-time**: gebruik per datum alleen waarnemingen die toen al gepubliceerd waren. CBS-maandcijfers komen ~30 dagen na maandeinde; schuif macro-series dus minimaal 1 maand op vóór je ze aan een target koppelt.
- **Log-transform voor prijzen**: `y_t = ln(x_t)` maakt rendementen optelbaar en stabiliseert variantie. Macro-sentimentsindicatoren (vertrouwen, saldi) niet loggen — die kunnen negatief zijn.

## 1. Rendement / groei (1e orde)

```python
ret_k   = x.pct_change(k)              # k-periode rendement
logret  = np.log(x).diff(k)            # log-rendement (prijzen)
yoy     = x.pct_change(12)             # jaar-op-jaar (maandseries, ontseizoent grotendeels)
```

## 2. Trend en cyclus (CBS Business Cycle Tracer-methode)

Het paper (CBS 09038) definieert de cyclus als afwijking van de langetermijntrend:

```python
trend = x.rolling(window=61, center=True, min_periods=25).mean()  # of HP-filter
cycle = x - trend
```

Voor live gebruik (geen toekomstdata!): centered window vervangen door eenzijdig venster of een causale filter (bijv. eenzijdige HP / EMA). De vier BCT-kwadranten als categorische feature:

```python
above  = cycle > 0
rising = cycle.diff() > 0
kwadrant = above*2 + rising   # 3=groen, 2=oranje, 1=geel, 0=rood
```

## 3. Normalisatie

**Z-score** — altijd met uitsluitend verleden data (expanding of rolling), anders lek je de toekomst:

```python
z = (x - x.expanding(min_periods=36).mean()) / x.expanding(min_periods=36).std()
z_roll = (x - x.rolling(120).mean()) / x.rolling(120).std()   # regime-gevoeliger
```

Alternatieven: **min-max** op rolling venster; **rank → gauss-rank** (robuust tegen uitschieters). Voor Numerai geldt bovendien: features per era **cross-sectioneel** ranken over het universum (elke datum krijgt zijn eigen ranking over alle tickers/coins), want de targets zijn cross-sectionele ranks.

## 4. Momentum en acceleratie (1e en 2e afgeleide)

```python
mom_k = z.diff(k)          # momentum: verandering over k periodes
acc_k = mom_k.diff(k)      # acceleratie: verandering van het momentum
```

Acceleratie op maandmacro is precies de "strengthening of the decline" die het CBS-paper in juli/okt 2008 wél zag maar niet kon kwantificeren — als feature vangt hij omslagpunten eerder dan momentum.

## 5. Hogere-orde afgeleiden en gladstrijken

Elke differentiatie versterkt ruis (~×2 per orde). Vuistregels:

- Eerst gladstrijken, dan differentiëren: `ema = x.ewm(span=6).mean()` en daarop `diff()`.
- 3e orde (jerk) alleen op gladde, lange series; meestal voegt het na acceleratie weinig toe.
- Savitzky-Golay (`scipy.signal.savgol_filter`) geeft afgeleiden en gladstrijken in één stap — maar let op: standaard is hij tweezijdig; gebruik voor live features de causale variant (fit op trailing venster).

## 6. Volatiliteit en stabiliteit

```python
vol   = logret.rolling(20).std() * np.sqrt(252)   # geannualiseerd (dagdata)
stab  = mom_k / vol                                # momentum per eenheid risico
drawdown = x / x.cummax() - 1
```

## 7. Interacties en regime-features

Interacties zijn producten/verhoudingen van al berekende features — puur ML-prep:

```python
f_int = z_macro_kwadrant * mom_asset      # asset-momentum geconditioneerd op macro-regime
f_lag = feature.shift(k)                   # lags: geef het model geheugen
```

Beperk je tot interacties met een economische reden (regime × momentum, vol × momentum); blind alle paren genereren geeft overfitting.

## 8. Reproduceerbaarheid en anti-leakage checklist

1. Pin de input: elke feature-run noteert de CID/state-root van de gebruikte ruwe series.
2. Alleen trailing/expanding vensters in live features; centered filters alleen voor onderzoek achteraf.
3. Respecteer publicatievertraging per bron (CBS ~30d, EDGAR filing-datum, prijzen T+0).
4. Eén deterministische feature-module, geversioneerd; geen handmatige tussenstappen.
5. Valideer met purged/embargoed walk-forward splits (geen k-fold op tijdseries).
