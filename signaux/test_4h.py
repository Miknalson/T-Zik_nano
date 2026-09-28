"""Test historique des 3 méthodes sur des bougies de 4 heures, avant tout ajout aux signaux.

Mêmes règles et mêmes réglages qu'en quotidien (aucun réglage retouché), mêmes frais
Libertex, même filtre anti-hasard. Yahoo ne fournit les cours horaires que sur 2 ans.
"""
import pandas as pd

import signaux as s


def bougies_4h(ticker):
    import yfinance as yf
    h = yf.download(ticker, period="729d", interval="1h", auto_adjust=True, progress=False)
    if isinstance(h.columns, pd.MultiIndex):
        h.columns = h.columns.get_level_values(0)
    h = h[["Open", "High", "Low", "Close"]].dropna()
    h.index = pd.to_datetime(h.index)
    if h.index.tz is not None:
        h.index = h.index.tz_convert("UTC").tz_localize(None)
    b = h.resample("4h").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    return b[b.index < pd.Timestamp.now(tz="UTC").tz_localize(None).floor("4h")]  # bougie en cours exclue


def main():
    lignes, valides, testees = [], 0, 0
    for ticker, nom, classe in s.MARCHES:
        try:
            df = bougies_4h(ticker)
        except Exception as exc:
            print(f"{nom:<13} données indisponibles : {exc}")
            continue
        for nom_regle, regle in s.REGLES.items():
            e = s.evaluer(df, regle(df), s.FRAIS[classe])
            testees += 1
            valides += e["valide"]
            etoile = " ★" if s.METHODE_SUIVIE.get(ticker) == nom_regle else ""
            lignes.append(f"{nom:<13} {nom_regle:<30} {len(df):>5} bougies  {e['nb_trades']:>4} trades  "
                          f"{e['rendement_annuel']:+7.1%}/an  p = {e['p']:.3f}  "
                          f"{'VALIDÉE' if e['valide'] else 'rejetée : ' + ', '.join(e['raisons'])}{etoile}")
    print("\n".join(lignes))
    print(f"\n4 heures : {valides} règle(s) validée(s) sur {testees}. "
          f"Par pur hasard, on en attendrait environ {testees * s.P_MAX:.1f}.")


if __name__ == "__main__":
    main()
