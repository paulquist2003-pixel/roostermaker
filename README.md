# Roostermaker

Een webapp die elke maand het rooster maakt voor een zorgteam met vroege, tussen-, late en nachtdiensten. De planner vult in zes stappen in wat er die maand speelt; het programma zoekt het rooster dat alle harde regels haalt en zo veel mogelijk voorkeuren.

Er staan **geen gegevens van medewerkers in deze repository**. Namen, voorkeuren en roosters staan alleen in de database op de server.

## Zo werkt het voor de planner

1. **Vorige maand**: de laatste 5 dagen van vorige maand (wordt automatisch ingevuld als die maand in de roostermaker staat).
2. **Uren uit ORTEC**: saldo eind vorige maand en verlofuren deze maand.
3. **Vakantie en vrij**: kies Vakantie, Vrij of Liever vrij en klik of sleep over de dagen.
4. **Vaste diensten**: de nachten van de vaste nachtdiensten en alles wat al afgesproken is.
5. **Rooster maken**: één knop, 10 tot 60 seconden.
6. **Rooster bekijken**: klik op een vakje om te wijzigen. De controle rekent meteen mee. Download het als Excel voor ORTEC of druk het af.

Het team (contract, vaste vrije dagen, diensten die iemand graag of liever niet doet, vaste afspraken) en de regels staan op de pagina's **Team** en **Instellingen**. Bij Instellingen kun je ook het oude Excel-bestand inlezen, een back-up maken en een verzonnen voorbeeldteam laden om te oefenen.

## Regels

Hard (wordt nooit overtreden):

- bezetting per dag en dienst; een dienst die echt niet te vullen is blijft open en wordt gemeld
- niet ingepland bij vakantie of een sterke wens, niet op een dag of dienst met "Nooit"
- hooguit 5 dagen achter elkaar, geen losse vrije dag tussen werkdagen (uit te zetten per persoon)
- geen vroege dienst na een late, na een nacht alleen nacht of vrij
- tussendiensten alleen waar de bezetting of de volgorde bij Instellingen het toestaat

Zacht (zo goed mogelijk): eindsaldo binnen de grens, weekuren naar rato, vaste vrije dagen, voorkeursdiensten, eerlijke verdeling van weekenden en open nachten, de teamvergadering op de 2e maandag.

De rekenkern (`app/solver.py`) is een lineair programma met gehele getallen (scipy `milp`, HiGHS). `app/checker.py` controleert een rooster los daarvan, zodat ook handmatige wijzigingen worden gecontroleerd.

## Gratis demo op Render

Voor een demo met het verzonnen voorbeeldteam (geen echte namen):

1. Maak een account op [render.com](https://render.com) en koppel GitHub.
2. Kies **New**, dan **Blueprint**, en selecteer deze repository. Render leest `render.yaml` (gratis, Frankfurt).
3. Vul bij `APP_PASSWORD` het wachtwoord voor de demo in en klik **Apply**.

Na een paar minuten staat de app op `https://roostermaker-demo.onrender.com` (of een vergelijkbaar adres). Let op:

- Na 15 minuten zonder bezoek valt de app in slaap. Het eerste bezoek daarna duurt ongeveer een minuut.
- Er is geen vaste opslag. Na de slaapstand begint de app opnieuw met het voorbeeldteam en een klaar rooster voor februari 2027.
- De gratis server is traag; rooster maken duurt daar langer dan op een betaalde server.

## Op Railway zetten (voor echt gebruik)

1. Nieuw project in Railway, **Deploy from GitHub repo**, kies deze repository. Railway bouwt met de `Dockerfile`.
2. Kies bij de service onder Settings een **EU-regio** (bijvoorbeeld Amsterdam).
3. Voeg een **Volume** toe aan de service met mount path `/data`. Zonder volume is alles na een herstart weg.
4. Zet onder **Variables**:
   - `APP_PASSWORD`: het wachtwoord dat de planners gebruiken
   - `SECRET_KEY`: een lange willekeurige tekst (bijvoorbeeld `${{secret(64)}}`)
   - `DATA_DIR`: `/data` (staat al in de Dockerfile)
5. Onder Settings, Networking: **Generate Domain**. Dat is het adres voor de planners.

Er draait bewust één proces: het rooster maken kost even rekenkracht en er wordt er maar één tegelijk gemaakt. 1 vCPU en 1 GB geheugen is genoeg.

## Lokaal draaien

```bash
pip install -r requirements-dev.txt
APP_PASSWORD=test uvicorn app.main:app --reload
pytest -q
```

## Privacy

- De app is alleen bereikbaar met het wachtwoord; de sessie is een ondertekend cookie (HTTPS, SameSite strict).
- Na 10 foute pogingen in een kwartier wordt inloggen vanaf dat adres even geblokkeerd.
- Lettertypen en scripts worden zelf geserveerd; de app laadt niets van andere sites.
- Gegevens staan in één SQLite-bestand op het volume. Van elk onderdeel worden de laatste 30 versies bewaard.
- Gebruik met echte namen pas na akkoord van de leidinggevende (AVG, verwerkersovereenkomst met de hostingpartij).

Lettertype: Atkinson Hyperlegible (SIL Open Font License, zie `app/static/fonts/OFL-LICENSE.txt`).
