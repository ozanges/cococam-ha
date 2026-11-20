# Publier et installer le dépôt

Le Supervisor clone le dépôt Git lui-même. Un dépôt GitHub public facilite l’installation, et GitHub Actions peut alors exécuter les tests sur amd64 et arm64. Un serveur Git interne est également possible si le Supervisor peut joindre son URL. [Dépôts d’applications Home Assistant](https://contributors.home-assistant.io/apps/guides/repository/)

1. Créer sur GitHub un dépôt vide nommé `cococam-ha`. Choisir la visibilité et laisser le dépôt vide à la création.
2. Copier son URL HTTPS. Depuis le dépôt local, ajouter cette URL et pousser la branche `main` avec le compte GitHub choisi.

```sh
git remote add origin https://github.com/VOTRE-COMPTE/cococam-ha.git
git push -u origin main
```

3. Dans GitHub, ouvrir **Actions → Vérifications**. La matrice construit deux images, amd64 et arm64, et valide le minuteur et les flux HLS avec une vidéo synthétique.
4. Suivre [l’installation par l’interface](README.md#installer-depuis-linterface). Saisir le compte CloudEdge dans la configuration de l’application, dans Home Assistant.
5. Sur le Pi, ouvrir **COCOCAM**, vérifier les deux vues et attendre la fin du compte à rebours. Vérifier que les deux vidéos s’arrêtent, que **Rouvrir le direct** demande un clic et que la caméra reprend sur ce clic. Fermer ensuite le panneau pendant plus de huit secondes pour vérifier la coupure liée au départ. Mesurer CPU et mémoire avec le flux arrêté, puis avec les deux vues actives.

## Mises à jour des dépendances

Installer [l’application GitHub Renovate](https://github.com/apps/renovate/installations/new) en lui donnant accès au seul dépôt COCOCAM. Renovate ouvre des pull requests pour le verrou Python, les images Docker, les actions GitHub, `hls.js` et le commit du client CloudEdge. Les bibliothèques installées par Debian ou Alpine sont rafraîchies lors des reconstructions de l’image.

Renovate peut fusionner les correctifs Python, les changements de digest des images de base et les mises à jour mineures des actions GitHub quand les contrôles réussissent. Les changements de MediaMTX, du lecteur `hls.js` ou du client CloudEdge passent par une revue manuelle. Avant de fusionner l’un de ces changements, vérifier sur une caméra le réveil, la lecture des deux vues et la coupure après expiration.

Après chaque changement dans `cococam/` fusionné sur `main`, le workflow **Publier l’image** choisit la prochaine version corrective disponible. Il construit et teste les deux variantes, publie le tag multiarchitecture sur GHCR, puis enregistre la version dans le manifeste Home Assistant. Le package GHCR doit être public pour que le Supervisor puisse le télécharger. **Run workflow** permet aussi de demander une reconstruction avec une nouvelle version, par exemple pour actualiser les paquets système. L'installation automatique reste un réglage de chaque instance Home Assistant.
