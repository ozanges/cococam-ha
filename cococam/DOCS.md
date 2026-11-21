# COCOCAM à la demande

Dans **Configuration**, saisir les identifiants CloudEdge de la caméra. Si le compte possède plusieurs caméras, saisir le nom exact de la COCOCAM. Pays et indicatif doivent correspondre au compte. La durée du direct est réglable de 15 à 300 secondes. Enregistrer et démarrer ou redémarrer l’application.

Depuis **Ouvrir l’interface Web** ou le panneau **COCOCAM** dans le menu latéral, attendre que les deux vues soient disponibles. **Prolonger** remet le minuteur à sa durée configurée. **Couper** arrête la session pour tous les spectateurs. Après expiration, cliquer sur **Rouvrir le direct** pour réveiller de nouveau la caméra.

La vidéo est diffusée en HEVC. Si l’interface indique que le lecteur ne prend pas ce format en charge, ouvrir Home Assistant dans un navigateur qui le décode.

## Batterie

L’application demande le niveau de la batterie à CloudEdge au démarrage puis toutes les trente minutes environ. Le panneau indique la dernière mesure récupérée et l’état de charge lorsqu’il est disponible. La mesure reste visible sans direct. L’heure affichée correspond à la récupération auprès de CloudEdge. Le dernier relevé est conservé sur disque.

Activer **Publier la batterie via MQTT** pour créer un capteur dans Home Assistant. Le broker doit être enregistré auprès du Supervisor (par exemple l’application Mosquitto broker) et l’intégration MQTT doit être configurée. Le capteur fournit le pourcentage, l’heure de récupération et l’état de charge lorsqu’il est connu.

## Vidéo dans un tableau de bord

Installer la carte `cococam-card.js` qui accompagne la version 0.1.3 du dépôt. Dans l’éditeur de tableau de bord, ajouter **COCOCAM en direct**, puis choisir l’objectif. Le [guide d’installation de la carte](https://github.com/ozanges/cococam-ha#vid%C3%A9o-dans-un-tableau-de-bord) détaille l’ajout de la ressource et l’identifiant de l’application.
