# COCOCAM à la demande pour Home Assistant

Deux vues COCOCAM dans le menu latéral de Home Assistant. Ouvrir la vue déclenche une seule session CloudEdge. La passerelle réutilise le transport KCP/VVP testé sur une COCOCAM B40AA avec le firmware 6.1.4.20251120, et republie la vidéo HEVC en HLS sans la réencoder.

## Installer depuis l’interface

1. Dans Home Assistant OS, ouvrir **Paramètres → Applications → Installer une application → ⋮ → Dépôts**. Ajouter l’URL Git du dépôt. Installer **COCOCAM à la demande**. Le Supervisor télécharge l’image préconstruite pour son architecture.
2. Dans **Configuration**, saisir l’e-mail et le mot de passe du compte CloudEdge. Indiquer le nom exact affiché dans CloudEdge si le compte possède plusieurs caméras. Enregistrer. Démarrer l’application ou la redémarrer si elle tournait déjà.
3. Ouvrir l’interface Web de l’application puis activer **Afficher dans la barre latérale**. Pour un raccourci dans un tableau de bord, ouvrir le panneau, copier son chemin Home Assistant et choisir l’action de navigation d’une carte Bouton vers ce chemin.

La barre latérale expose le panneau aux administrateurs. Home Assistant authentifie la lecture via Ingress. Les ports vidéo et de contrôle du serveur média restent internes au conteneur. L’adresse du compte CloudEdge et le mot de passe restent dans les options locales de l’app et ne figurent pas dans ce dépôt.

## Vidéo dans un tableau de bord

Avec l’application 0.1.3 ou ultérieure, copier [cococam-card.js](dashboard/cococam-card.js) dans le répertoire `www` de Home Assistant, puis ajouter `/local/cococam-card.js` comme **Module JavaScript** dans **Paramètres → Tableaux de bord → Ressources**. L’option Ressources apparaît en mode avancé. Si le dossier `www` vient d’être créé, redémarrer Home Assistant pour activer `/local/`. Recharger le navigateur puis ajouter la carte **COCOCAM en direct** dans l’éditeur du tableau de bord.

Choisir **Vue 1**, **Vue 2** ou **Les deux vues**. L’identifiant de l’application est `ae189e14_cococam` pour la version installée depuis ce dépôt. Pour une installation locale ou depuis un fork, reprendre le dernier segment du chemin `/app/…` affiché par Home Assistant lorsque le panneau COCOCAM est ouvert.

La carte démarre à partir de **Voir le direct** et applique la durée et la coupure de la passerelle. Elle utilise le même accès Ingress administrateur que le panneau. Le choix des vues contrôle les pistes lues par le navigateur. Les deux objectifs de la caméra partagent toujours une session CloudEdge.

## Ouverture et coupure

- Ouvrir le panneau latéral démarre la caméra au repos. La carte de tableau de bord démarre au clic. Le compteur commence quand les deux pistes sont disponibles.
- Le direct dure 60 s par défaut. **Prolonger** remet le compteur à sa durée configurée. **Couper** arrête la session pour tous les spectateurs.
- À l’expiration, la lecture se ferme et la caméra reste en pause jusqu’à un clic sur **Rouvrir le direct**. Une reconnexion du navigateur ou un rafraîchissement du panneau ne prolonge pas la session.
- En quittant l’interface, la dernière connexion ferme le direct après huit secondes. Une connexion disparue est détectée par le WebSocket, puis ce délai s’applique.
- Le démarrage dispose d’un délai maximal distinct de 110 secondes. Un échec ou une déconnexion de la caméra demande une nouvelle action de l’utilisateur.

## Exécuter hors Home Assistant

Avec Docker Compose, copier `options.example.json` vers `options.local.json` et éditer la copie locale.

```sh
docker compose up --build -d
```

Ouvrir `http://127.0.0.1:8099/` depuis la machine qui héberge Docker. En mode autonome, garder cette interface sur la boucle locale. Pour arrêter le conteneur, utiliser `docker compose down`.

## Vérifier

L’intégration à Home Assistant OS cible `aarch64` (Pi 4 en 64 bits) et `amd64`. Le module média ouvre une seule session caméra, joint chaque série à son premier point d’accès HEVC et remuxe en HLS via MediaMTX. Le lecteur doit prendre en charge le HEVC. Les performances sur Pi 4, la compatibilité réseau dans le conteneur HA et la lecture dans le navigateur cible se vérifient au premier déploiement.

```sh
docker build -t cococam-ha:test cococam
docker run --rm --network none -e COCOCAM_MEDIA_TEST=1 -e PYTHONPATH=/opt/cococam \
  -v "$PWD:/workspace:ro" -w /workspace cococam-ha:test \
  python -m unittest discover -s tests -v
```

Le test média utilise un signal vidéo synthétique local. Il vérifie les deux sorties HLS et leur coupure conjointe. [Panneau Ingress](https://contributors.home-assistant.io/apps/guides/ingress/) · [HEVC et navigateurs](https://www.home-assistant.io/integrations/stream/#technical-details)

Le client de session est basé sur [hass-cloudedge-meari](https://github.com/saidtezel/hass-cloudedge-meari) au commit `4f52459653aa65d246f5d7421fbab8bac0a4af26`. Sa licence MIT est conservée dans l’image, sous `/opt/meari/LICENSE`.
