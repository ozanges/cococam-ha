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

L’installation native a besoin d’un accès sortant pour construire l’image et ouvrir une session CloudEdge. L’image de la première version est construite sur le Pi. Aucun registre d’images du projet n’est requis.
