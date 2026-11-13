# Spec — App de veille arXiv

La spec vit dans le doc Claude : https://claude.ai/artifact/UwA6F5SyJoEBed6hUUdTYy

**À faire :** remplacer ce fichier par l'export Markdown du doc (menu sous le nom du doc → Export → Markdown), pour que la spec soit lisible hors ligne et versionnée avec le code.

Résumé de ce qui compte pour le code, en attendant :

- Une édition par jour, N articles (8 par défaut), un emplacement exploration toujours présent.
- Pipeline : ingestion arXiv → présélection sans IA → classement (modèle rapide) → texte complet (HTML, LaTeX, PDF, résumé) → génération (modèle fort) → vérification (appel séparé) → publication.
- Tout contenu est sourcé : chaque affirmation renvoie à un passage de l'article ; aucun chiffre inventé.
- Infrastructure gratuite hors API Claude : GitHub Actions (dépôt privé), Supabase, app Android Expo.
- Ordre de construction : 1) pipeline local en JSON, 2) schéma Supabase, 3) workflows GitHub Actions, 4) app Android, 5) V2 puis V3.
- Demander avant toute dépense ou tout choix d'hébergement.
