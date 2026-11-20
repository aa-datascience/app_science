# Vérifications sur le téléphone — APK n° 2 (figures et notifications)

À faire une fois l'APK installé, avant de commencer la V2. Pour chaque point : ça marche, ça ne marche pas, ou ce qui gêne. Une capture d'écran aide quand quelque chose cloche.

## 0. Installation

- [ ] Ouvrir le lien du build sur le téléphone, télécharger l'APK, autoriser l'installation depuis le navigateur.
- [ ] L'app s'installe sous le nom « arXiv Digest » et s'ouvre sans Expo Go ni ordinateur allumé.
- [ ] Connexion avec le compte Supabase.
- [ ] À la connexion, Android demande l'autorisation d'envoyer des notifications : accepter.
- [ ] Onglet Settings : la section Notifications indique « On ».

## 1. Cartes et figures

- [ ] Les cartes défilent d'un glissement horizontal, une par écran, avec la progression (2/8).
- [ ] Une carte dont l'article a des figures en montre une en haut, sur fond blanc, nette et entière.
- [ ] Une carte sans figure s'affiche normalement, sans espace vide en haut.
- [ ] La figure choisie illustre bien le résultat annoncé par la carte (à juger sur trois ou quatre cartes).

## 2. Plein écran et zoom

- [ ] Un appui sur la figure l'ouvre en plein écran.
- [ ] Pincer avec deux doigts agrandit la figure ; elle reste nette.
- [ ] Une fois agrandie, un doigt la déplace.
- [ ] Un double appui agrandit, un second double appui revient à la taille d'origine.
- [ ] Le bouton Close et le bouton retour d'Android ferment le plein écran.

## 3. Vue profondeur

- [ ] Ouvrir un article jamais ouvert : « Preparing this paper… », puis le contenu en moins d'une minute.
- [ ] La section Figures montre une à trois figures, chacune avec « Fig. N », une phrase qui dit quoi regarder, et la légende.
- [ ] Les formules des légendes et de la version Physicist sont mises en forme (pas de `$` visibles).
- [ ] Les figures à plusieurs panneaux montrent tous leurs panneaux.
- [ ] Rouvrir le même article : affichage immédiat, sans attente.

## 4. Hors ligne

Ouvrir l'édition et un ou deux articles avec le réseau, puis passer en mode avion.

- [ ] L'accueil indique que l'édition affichée est celle gardée sur l'appareil.
- [ ] Les cartes s'affichent, avec leurs figures.
- [ ] Un article déjà ouvert s'affiche, avec ses figures.
- [ ] Un article jamais ouvert affiche « You seem to be offline » et propose de réessayer.
- [ ] Donner un feedback hors ligne (Interesting, Save), puis couper le mode avion : rien ne plante. Je vérifierai de mon côté que le feedback est arrivé en base.
- [ ] Limite connue : hors ligne, des formules jamais affichées auparavant apparaissent en LaTeX brut.

## 5. Notifications

Je les déclenche à la main pour l'essai ; dites-moi quand vous êtes prêt.

- [ ] Notification du matin reçue : « Today's edition is ready — N papers ».
- [ ] Un appui sur la notification ouvre l'app.
- [ ] Rappel du soir reçu, avec le bon nombre d'articles restants.
- [ ] Après avoir terminé l'édition, aucun rappel du soir n'arrive.
- [ ] Les jours suivants : une notification vers 7 h 35, un rappel vers 20 h 05 si l'édition n'est pas finie, et rien d'autre.

## 6. Confort

- [ ] Taille du texte, marges, lisibilité en mode sombre.
- [ ] Boutons de feedback faciles à toucher.
- [ ] Rien qui ressemble à une incitation à continuer après l'écran de fin.

# Vérifications sur le téléphone — APK n° 4 (V2 : carnet, stats, profil)

Build : https://expo.dev/accounts/aa-datascience/projects/arxiv-digest/builds/d9c230f5-dd61-40f7-94a3-8b1ad3f30273

## 7. Carnet

- [ ] La barre du bas montre quatre onglets : Today, Notebook, Stats, Settings.
- [ ] Notebook liste les articles déjà sauvegardés.
- [ ] Save sur une carte : l'article apparaît dans Notebook ; un second appui sur Save l'en retire.
- [ ] Fiche d'un article : écrire une note et des tags, « Save note and tags », revenir : ils sont dans la liste.
- [ ] La recherche trouve un mot de la note, du titre ou un auteur ; un appui sur un tag filtre la liste.
- [ ] « Read the explanation » ouvre la vue profondeur d'un article d'une ancienne édition, avec son titre.
- [ ] Export Markdown, puis BibTeX : le menu de partage d'Android s'ouvre, et le fichier reçu est lisible.
- [ ] « Remove from notebook » (deux appuis) retire l'article ; sur la carte du jour, Save n'est plus actif.
- [ ] En mode avion : la liste s'affiche, avec la mention hors ligne.

## 8. Stats

- [ ] Le tableau par semaine et les barres par sous-catégorie s'affichent ; 4, 8 et 12 semaines changent la période.
- [ ] Les chiffres de la semaine correspondent à ce qui a été lu.
- [ ] Lundi : une page « Last week » précède la première carte ; « Start › » mène à la carte 1/N.

## 9. Profil

- [ ] Settings → « Open profile » : poids des catégories et des mots-clés, avec la raison du dernier changement.
- [ ] Changer le nombre d'articles, « Save changes » : l'édition du lendemain a ce nombre d'articles.
- [ ] Changer l'heure du matin : la notification du lendemain arrive dans l'heure qui suit l'heure choisie.
- [ ] Verrouiller un poids, enregistrer, rouvrir l'écran : il est toujours « Locked ».
- [ ] Suivre une catégorie de plus, enregistrer : elle apparaît dans la liste.
- [ ] Le lendemain d'un « Interesting » ou d'un Save : le poids de la catégorie a monté, avec sa raison.
- [ ] En mode avion : l'écran s'affiche, et l'enregistrement dit qu'il a échoué.

## 10. APK n° 6 : nouvelle édition et widget

- [ ] Laisser l'app ouverte sur une carte (par exemple la 3e), la rouvrir le lendemain : l'édition du jour commence à la première carte (ou à « Last week » le lundi).
- [ ] Appui long sur l'écran d'accueil → Widgets → arXiv Digest → « Reading streak » : le widget se pose et affiche la série, l'état du jour et une barre par jour.
- [ ] Ouvrir un article, revenir à l'écran d'accueil : le chiffre du jour a augmenté.
- [ ] Voir toutes les cartes du jour : l'initiale du jour passe en doré et la série augmente de 1.
- [ ] Le lendemain, sans ouvrir l'app : le widget montre la nouvelle édition « waiting » (mise à jour au plus une heure après son arrivée).
- [ ] Toucher le widget ouvre l'app.

# Vérifications sur le téléphone — APK n° 7 (V2, étape 4 : concepts et questions)

## 11. Concepts et questions

- [ ] La barre du bas montre cinq onglets : Today, Notebook, Concepts, Stats, Settings.
- [ ] Ouvrir un article jamais ouvert : après « Preparing this paper… », la vue montre une section Concepts (pastilles) et une section Questions.
- [ ] Une pastille ouvre la fiche du concept : bascule Simple / Expert, formules mises en forme, articles où il apparaît.
- [ ] QCM : un appui sur une option affiche « Correct » ou « Not quite », la bonne option encadrée, l'explication et le passage de l'article. Vérifier aussi une option qui contient une formule.
- [ ] Réponse courte : « Show answer », puis « I had it » ou « I didn't » ; en revenant sur l'article, la réponse est gardée.
- [ ] « Try again » repose la question.
- [ ] En mode avion : répondre à une question, couper le mode avion : rien ne plante (je vérifierai que la réponse est arrivée en base).
- [ ] Un article ouvert avant le 20 novembre : la phrase « written before concepts and questions existed » et le bouton « Regenerate this explanation » ; deux appuis le refont (environ 0,01 $), avec concepts et questions.
- [ ] Onglet Concepts : la liste et la recherche ; « Merge a duplicate » sur une fiche (seulement si un vrai doublon existe).
- [ ] Stats : section « Learning » (questions réussies, nouveaux concepts) ; écran de fin : ligne « new concepts » les jours où il y en a.
- [ ] Les questions portent sur la physique de l'article, pas sur des détails sans intérêt (à juger sur trois ou quatre articles).
