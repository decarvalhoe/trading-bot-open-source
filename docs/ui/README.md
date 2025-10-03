# Design system léger pour les interfaces de trading

Ce design system fournit une base cohérente pour les micro-fronts du projet. Il est centré sur
l'affichage des informations financières critiques tout en respectant l'accessibilité et un
langage visuel sombre orienté données.

## Principes

1. **Lisibilité avant tout** : utiliser des contrastes élevés (minimum WCAG AA) et des polices sans
   empattement pour éviter la fatigue visuelle.
2. **Hiérarchie claire** : titres, sous-titres et contenu utilisent des niveaux typographiques
   distincts (`heading--xl`, `heading--lg`, `heading--md`, `text`).
3. **Signalement rapide du risque** : les badges (`badge--success`, `badge--warning`,
   `badge--critical`, `badge--info`, `badge--neutral`) reprennent une palette inspirée des
   conventions de marché pour attirer l'œil sur les alertes.
4. **Responsive par défaut** : tous les composants sont pensés pour une lecture sur desktop et
   mobile.

## Tokens

| Nom                 | Valeur par défaut              | Usage principal                                     |
| ------------------- | ------------------------------ | --------------------------------------------------- |
| `--color-bg`        | `#0f172a`                       | Fond global sombre                                  |
| `--color-surface`   | `#111c3b`                       | Cartes et panneaux                                  |
| `--color-border`    | `rgba(255,255,255,0.08)`        | Contours discrets                                   |
| `--color-text`      | `#f8fafc`                       | Texte principal                                     |
| `--color-text-muted`| `#94a3b8`                       | Texte secondaire                                    |
| `--color-success`   | `#22c55e`                       | Badges achat / succès                               |
| `--color-warning`   | `#f97316`                       | Badges vente / avertissements                       |
| `--color-critical`  | `#ef4444`                       | Alertes critiques                                   |
| `--color-info`      | `#38bdf8`                       | Informations neutrales ou statut « à traiter »     |
| `--radius-md`       | `12px`                          | Cartes                                              |
| `--radius-sm`       | `8px`                           | Badges, éléments d'alerte                           |
| `--shadow-sm`       | `0 12px 30px rgba(15, 23, 42, 0.35)` | Profondeur légère                             |
| `--space-xs/sm/md/lg/xl` | `0.25rem` → `2.5rem`      | Échelle de spacing                                  |

## Composants partagés

### Carte (`.card`)
Conteneur principal pour blocs de contenu (portefeuilles, transactions, alertes). Inclut un
`card__header` et `card__body` avec padding normalisé et bordure subtile.

### Tableau responsif (`.table`)
Tableaux collapsables sur mobile : l'en-tête est masqué et les cellules affichent une étiquette via
`data-label`.

### Liste d'alertes (`.alert-list`)
Affiche les alertes avec un statut coloré et un contenu détaillé. Le layout utilise une grille pour
aligner badge et description.

### Badges (`.badge`)
Indicateurs d'état à utiliser pour les tags, les statuts de transaction, la sévérité des alertes.
Le composant existe en variantes `success`, `warning`, `critical`, `info`, `neutral`.

### Typographie (`.heading`, `.text`)
Quatre niveaux pour les titres et un style `text--muted` pour les éléments secondaires.

## Accessibilité

- **Couleurs** : vérifier que tout texte sur un fond coloré conserve un ratio de contraste ≥ 4.5:1.
  Les badges critiques et avertissements sont déjà calibrés. Adapter les variantes si de nouvelles
  couleurs sont ajoutées.
- **Structure sémantique** : utiliser les balises HTML5 (`<header>`, `<main>`, `<section>`,
  `<table>`) et des attributs ARIA (`aria-labelledby`, `role="grid"`) comme dans le tableau et la
  liste d'alertes.
- **Navigation clavier** : éviter de rendre non focusables des éléments interactifs. Les badges ne
  doivent pas devenir des boutons sans gestion de focus.
- **Internationalisation** : préférer les formats `strftime` localisés et les chaînes issues de
  fichiers de traduction lorsque le contenu n'est pas statique.

## Bonnes pratiques d'implémentation

- Conserver tous les styles spécifiques dans `/app/static/styles.css` et dériver les nouvelles vues
  à partir des classes existantes.
- Factoriser les nouveaux composants partagés dans des macros Jinja2 ou des composants front-end si
  un framework est utilisé.
- Tester les contrastes avec les outils intégrés des navigateurs (ex. Lighthouse).
- Documenter toute extension de design system dans un fichier Markdown complémentaire au présent
  document et référencer l'usage dans le code.
