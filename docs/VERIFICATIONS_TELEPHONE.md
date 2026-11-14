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
