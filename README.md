# Jednoduchý výpočet izolace

Pythonový desktopový nástroj pro stacionární přenos tepla vícevrstvou rovinnou stěnou nebo válcovou izolací. Potřebuje Python 3 a Tkinter, další balíčky nejsou potřeba.

Spuštění ve složce projektu:

```powershell
python app.py
```

Na některých instalacích Pythonu je nutné Tkinter doinstalovat samostatně. Testy: `python -m unittest -v`.

## Použití

1. Vyberte válec nebo rovinu. Zadejte teplotu **vnitřního povrchu izolace**, teplotu okolí, rozměry, součinitel přestupu tepla prouděním a emisivitu vnějšího povrchu.
2. Přidejte vrstvy od vnitřní po vnější. Průměr válce je průměr **pod první vrstvou izolace**, nikoli vnější průměr po zaizolování. U válce je délka použita pro celkovou ztrátu; u roviny plocha.
3. Klikněte na **Vypočítat**. Zobrazí se teploty rozhraní, teplota povrchu, ztráta, celkový součinitel prostupu tepla U a tepelný odpor R, barevný řez a graf průběhu teploty od vnitřního povrchu přes všechny vrstvy. U i R zahrnují vrstvy a vnější přestup tepla a jsou vztažené k vnitřní ploše izolace (u roviny k zadané ploše, u válce k ploše pod první vrstvou). Modrá křivka v grafu zobrazuje součinitel teplotní vodivosti λ podle pravé osy. Oba průběhy zohledňují zadanou lambda(T); u válce počítají radiální průběh.
4. V dialogu **Materiály…** můžete upravit existující materiál nebo tlačítkem **Nový** vytvořit další. Zadejte jeden řádek `teplota; lambda` pro konstantní vodivost, nebo několik řádků se vzestupnými teplotami pro závislost na teplotě. Desetinná tečka i čárka jsou podporovány. Uložení přepíše databázi `materials.json` vedle skriptu; složka tedy musí být zapisovatelná.
5. Ve stejném dialogu lze zadat cenu v Kč/m² a referenční tloušťku, pro kterou cena platí, bez DPH. Výpočet ceny poměrně přepočítá zadanou tloušťku a plochu vrstvy (u válce podle středního poloměru). Materiály bez zadané ceny se vypíší jako neoceněné a součet bude označen jako neúplný. Výsledek nezahrnuje prořez, spojovací materiál, oplechování ani montáž.

Přednastavený příklad 50 mm keramického vlákna a 250 mm minerální vlny používá průměr 500 mm, délku 1 m, okolí 20 °C, h = 5 W/(m²·K) a emisivitu 0,8. To jsou jen **zvolené vstupy**, nikoli údaje o konkrétním zařízení.

## Důležitá omezení

**Předvyplněné hodnoty lambda jsou pouze ilustrativní a nepředstavují ověřené údaje Sibralu, Rockwoolu ani jiného konkrétního výrobku. Výsledek s nimi není podkladem pro návrh ani bezpečnostní posouzení.** Doplňte hodnoty a maximální pracovní teploty z technických listů konkrétních výrobků; program mezní pracovní teplotu nekontroluje. Zohledněte také zdravotní a bezpečnostní požadavky na použité materiály.

- Lambda se mezi body lineárně interpoluje a přes každou vrstvu integruje podle teploty. Mimo tabulku se použije nejbližší krajní hodnota a zobrazí se varování. Jeden bod představuje konstantní lambda bez omezení rozsahu.
- Model předpokládá ustálený jednorozměrný přenos, dokonale přiléhající vrstvy a stejnou teplotu okolního vzduchu a okolních ploch pro sálání. Zadané h popisuje jen proudění; sálání se počítá samostatně. Hodnota h závisí na orientaci, geometrii a proudění vzduchu a není automaticky stanovena.
- Nezahrnuje tepelné mosty, podpěry, konce válce, spoje, mezery, plášť, kontaktní odpory, vlhkost, časový průběh ani teplotní pokles na vnitřní straně. Vnitřní teplota je teplota povrchu pod izolací, nikoli nutně teplota média.
- Při práci s horkými zařízeními, posuzování dotykové teploty a návrhu požární ochrany je nutné použít odpovídající normy a kvalifikované posouzení.
