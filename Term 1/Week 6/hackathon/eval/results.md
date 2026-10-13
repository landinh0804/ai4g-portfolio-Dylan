# Evaluation: models vs. human labels

50 hand-labelled posts (37 personal, 13 news). The labeller saw the text only, not the model outputs.

| | agreement | Cohen's κ | personal | news |
|---|---|---|---|---|
| Model 1 (german-sentiment-bert) | 50% (25/50) | 0.11 | 51% (19/37) | 46% (6/13) |
| Model 2 (twitter-xlm-roberta) | 54% (27/50) | 0.18 | 57% (21/37) | 46% (6/13) |
| Baseline (SentiWS word list) | 54% (27/50) | 0.25 | 62% (23/37) | 31% (4/13) |
| Model 1 vs Model 2 | 66% | | | |

κ: 0 = chance level, 1 = perfect. With 50 posts, differences of a few posts are noise.

Human labels: negative 23, neutral 23, positive 4. Not about rail: 9/50.

## Confusion matrix: Model 1 (german-sentiment-bert)

| human ↓ / predicted → | negative | neutral | positive |
|---|---|---|---|
| **negative** | 15 | 8 | 0 |
| **neutral** | 12 | 9 | 2 |
| **positive** | 1 | 2 | 1 |

## Confusion matrix: Model 2 (twitter-xlm-roberta)

| human ↓ / predicted → | negative | neutral | positive |
|---|---|---|---|
| **negative** | 15 | 7 | 1 |
| **neutral** | 9 | 12 | 2 |
| **positive** | 0 | 4 | 0 |

## Confusion matrix: Baseline (SentiWS word list)

| human ↓ / predicted → | negative | neutral | positive |
|---|---|---|---|
| **negative** | 12 | 8 | 3 |
| **neutral** | 3 | 14 | 6 |
| **positive** | 1 | 2 | 1 |

## Disagreements (32 posts where a model differs from the human)

| kind | human | M1 | M2 | SentiWS | text |
|---|---|---|---|---|---|
| news | positive | neutral (0.88) | neutral (0.83) | positive (0.42) | Eine gute Bahn plötzlich im Bereich des Möglichen? Kommentar zur aktuellen Preissenkung https://www.merkur.de/wirtschaft/deutsche-bahn-senkt-preise-fuer-abokarten-pendler-familienticket-kommentar-9453 |
| news | negative | negative (1.00) | neutral (0.54) | negative (-0.37) | Unfall in Deisenhofen - Auto und Regionalzug stoßen zusammen  #BRB #Bahnverkehr #Bahnübergang #Deisenhofen #Ersatzverkehr #Holzkirchen #Oberland #Unfall #Verspätungen #Zugausfall https://bahnblogstell |
| personal | neutral | negative (0.98) | neutral (0.63) | neutral (0.00) | Da bündeln die Bahn und die Autobahn GMBH Bauarbeiten. Im Kreuz Kaiserberg werden Brücken neugebaut, deshalb ist die Bahnstrecke gesperrt, und die Bahn nutzt die Pause gleich mit. Mein Zug nach Arnhem |
| news | negative | neutral (1.00) | neutral (0.94) | neutral (0.00) | Der 💩Fascho-Landtagspräsident hat die Wahl: Ausländischer Dienstwagen oder Deutschlandticket 🤡  www.t-online.de/nachrichten/... |
| personal | neutral | negative (0.98) | negative (0.89) | neutral (0.00) | Im Flixtrain erst mal lange Durchsagen darüber, welche Fahrscheine alle nicht zur Fahrt mit diesem Zug berechtigen. Zugbegleiterin muss dabei schon um 08:30 Uhr viel seufzen. We feel you! 🫶 |
| personal | neutral | negative (0.75) | neutral (0.63) | positive (0.48) | Wer auf dem Weg in den Urlaub die Tasche mit Portemonnaie, Papieren, etc zuhause vergisst, gewinnt eine Taxifahrt vom (zum Glück noch innerstädtischen!) nächsten Bahnhof zurück nach Hause und wieder z |
| personal | neutral | negative (0.81) | negative (0.68) | positive (0.11) | Hatte Deutschlandticket Urlaub ab Nürnberg geplant:  Magdeburg, Leipzig, Rostock, Warnemünde, Stralsund, Hiddensee, Schwerin, Potsdam  Aber ernsthaft - zu Faschos fahr ich nicht*  Jetzt wird's Kassel, |
| personal | negative | negative (0.99) | positive (0.63) | negative (-0.15) | Ja, manchmal vergesse ich, dass ich bei meinen Beiträgen auch Kontext liefern sollte 🫠  Danke! Gegenwärtig kämpfen wir bereits beim zweiten Zug mit erheblicher Verspätung |
| personal | neutral | neutral (0.99) | negative (0.60) | neutral (0.00) | Da gilt das Deutschlandticket nicht mehr oder??? 👉👈 |
| personal | negative | neutral (1.00) | neutral (0.93) | neutral (0.00) | 09.10.2026, 10:12 Uhr: 🚆 Schienenersatzverkehr auf der Linie RE30. 🚆 Gültig ab 09.10.2026 00:10 bis 13.10.2026 00:30Aufgrund von Bauarbeiten kommt es in der Zeit von Freitag, 09.10.2026, ca. 00:10 Uhr |
| personal | negative | negative (0.92) | neutral (0.68) | negative (-0.11) | Zug Siegen-Hagen: Und das nächste Desaster - Ersatzbus statt Bahn noch wochenlang https://www.wp.de/lokales/siegen-und-umland/article413364588/von-siegen-nach-hagen-bahnchaos-auf-der-ruhr-sieg-strecke |
| personal | positive | negative (0.80) | neutral (0.76) | negative (-1.05) | Bodenseegürtelbahn: Machen Akku-Züge die teure Oberleitung im Diesel-Loch überflüssig? https://www.suedkurier.de/kreis-konstanz/bodenseeguertelbahn-machen-akku-zuege-die-teure-oberleitung-im-diesel-lo |
| personal | negative | neutral (1.00) | negative (0.90) | negative (-0.34) | Der #Pfaffensteigtunnel ist nicht nur verkehrspolitisch fragwürdig und finanziell problematisch. Auch seine #Klimabilanz ist verheerend. Allein für den Bau werden nach vorliegenden Berechnungen rund 6 |
| personal | neutral | negative (0.94) | negative (0.56) | neutral (0.01) | Epilog: Wir mussten ja noch zurück nach Steinach im Wipptal. Also von St. Anton mit dem Bus nach Gossensaß und dort in den Zug.  Nein, doch nicht, Streik der italienischen Eisenbahner, keinerlei Zugve |
| personal | neutral | negative (0.84) | neutral (0.72) | neutral (0.00) | Ich packe meinen Koffer … zum Onlineparteitag  Ihr kennt das: Kein Koffer, kein Zug, kein Klapphocker, kein Aufzug ohne TÜV. Online-Parteitage sind bei uns seit Jahren Alltag, …  #Bundesparteitag #oBP |
| personal | negative | neutral (1.00) | neutral (0.76) | neutral (0.00) | Der dazugehörige Bahnsteig ist ausschließlich durch eine Fußgängerunterführung und eine steile Treppe zu erreichen. Auf der anderen Seite des Bahnsteigs liegt ein drittes, schon lange stillgelegten Au |
| personal | negative | neutral (1.00) | negative (0.73) | negative (-0.76) | Das rheinseitige, flussaufwärts führende Gleis ist über den dahinter liegenden Dorfplatz mehr schlecht als recht barrierefrei zu erreichen. Am eigentlichen Aufgang zum Bahnsteig ist eine steile Treppe |
| news | neutral | negative (0.97) | negative (0.89) | negative (-0.59) | Die AfD ist wirklich das dümmste was im Bundestag rumsitzt.  414 Abgeordnete stimmten dafür, 134 dagegen. Mit Nein votierte die AfD, die eine namentliche Abstimmung beantragt und gefordert hatte, anst |
| news | neutral | negative (0.91) | negative (0.62) | negative (-0.86) | "Unsere Erfahrung hat uns gelehrt, die Flugbahn der Drohnen zu verfolgen. Wenn sie etwa 10 Minuten vom Zug entfernt sind, kündigen wir die Evakuierung des Zugs an. Das kommt bei den Passagieren nicht  |
| news | positive | positive (0.77) | neutral (0.83) | neutral (0.01) | Es gibt noch positive Nachrichten: https://www.spiegel.de/mobilitaet/bus-bahn/hamburg-hannover-deutsche-bahn-plant-neubaustrecke-bundestag-beschliesst-auftrag-a-07c7f87b-074d-4a81-b506-57deafeb8395 |
| news | positive | neutral (0.99) | neutral (0.86) | neutral (0.00) | www.spiegel.de headline change  https://www.spiegel.de/mobilitaet/bus-bahn/hamburg-hannover-deutsche-bahn-plant-neubaustrecke-bundestag-beschliesst-auftrag-a-07c7f87b-074d-4a81-b506-57deafeb8395#ref=r |
| personal | neutral | negative (1.00) | neutral (0.65) | neutral (-0.01) | Die Reisenden nebenan holen labrige, bleiche Toast-Sandwiches aus der Plastikverpackung und spülen sie mit kaltem Kaffee aus der Dose runter. Ich geniesse mein selbst gebackenes #Sauerteigbrot zuerst  |
| personal | negative | neutral (0.53) | negative (0.63) | negative (-0.66) | Nur 13 statt 21 Strecken bis 2031: Bahn und Bund kürzen Sanierung des Schienennetzes  www.upday.com/de/news/nur-...  Aber Hauptsache für die Autobahnen ist immer genug Geld da. So macht man ÖPNV auch  |
| personal | neutral | neutral (0.98) | negative (0.86) | neutral (0.00) | Francia tiene la fama, pero realmente es Alemania quien pone trabas a la competencia:  "un tribunal declaró ilegal, mediante una resolución provisional inapelable, la disposición que obligaba a DB Inf |
| personal | negative | neutral (0.95) | neutral (0.69) | positive (0.27) | Deutschlandticket darf nicht teurer werden!  changing-cities.org/deutschlandt...  Crossposted with @openvibe.social |
| personal | neutral | positive (0.56) | positive (0.85) | positive (0.65) | Der Zugbegleiter hat wirklich sehr viel Freude daran „LudwigsLUST“ zu sagen. 😏 |
| personal | neutral | positive (1.00) | positive (0.94) | positive (1.34) | Erstens, ich mag Linz einfach voll gerne, und zweitens, es ist mit dem Zug so super gut und schnell erreichbar! 🙏❤️😊 |
| personal | neutral | negative (0.94) | negative (0.86) | neutral (0.00) | Wie kommen Sie bitte darauf, dass ich keine Fahrkarte habe? 😳  *zeigt Fahrkarte*  Wie sollen die Menschen denn ohne Fahrkarte auf den Bahnsteig stürmen? Schon Lenin sagte soch, dass wir Deutschen nich |
| news | negative | neutral (0.97) | negative (0.78) | negative (-1.01) | Ungleiche Förderung: Sprit wird billiger, Deutschlandticket teurer  Das Nahverkehrsabo kostet nächstes Jahr 66,80 Euro im Monat. Derweil steckt der Bund viel Geld in den Tankrabatt. Eine falsche Prior |
| news | neutral | negative (1.00) | neutral (0.62) | neutral (0.00) | Brandstiftung an Bahnstrecke in der Schweiz / Zug erfasst Pkw-Anhänger / Bahnhof Bad Nauheim wegen Geruchs gesperrt  #Bahnhofssperrung #Bahnverkehr #Bra https://bahnblogstelle.com/264090/brandstiftung |
| personal | neutral | negative (0.95) | negative (0.83) | neutral (-0.03) | Nachts alleine im RE1 🤫  Ich war auf dem Heimweg von einer Party und der Zug war fast komplett leer. Irgendwie hat mich die Vibration der Fahrt so angetörnt, dass ich meine Hand in die Jeans geschoben |
| personal | negative | negative (1.00) | neutral (0.69) | negative (-0.48) | 20:00 Uhr – 207 Fernzüge: Davon sind 116 im Schnitt 26 Minuten verspätet. #Bahn #Verspätung https://verspaetung.net |
