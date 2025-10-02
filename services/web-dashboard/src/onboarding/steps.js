export const STEP_LIBRARY = [
  {
    id: "connect-broker",
    title: "Connexion broker",
    description:
      "Renseignez les clés API ou OAuth pour relier votre compte broker et synchroniser vos portefeuilles.",
    tooltip:
      "Une connexion réussie permet de récupérer automatiquement soldes, positions et historique d'ordres.",
    videoUrl: "https://www.youtube-nocookie.com/embed/ysz5S6PUM-U",
    videoTitle: "Connecter un broker",
  },
  {
    id: "create-strategy",
    title: "Créer une stratégie",
    description:
      "Assemblez vos indicateurs, conditions d'entrée/sortie et règles de gestion du risque pour générer un plan trading.",
    tooltip:
      "Utilisez l'assistant IA ou le designer visuel pour accélérer la mise en place tout en gardant la main sur les paramètres.",
    videoUrl: "https://www.youtube-nocookie.com/embed/2alg7MQ6_sI",
    videoTitle: "Composer une stratégie",
  },
  {
    id: "run-first-test",
    title: "Premier backtest",
    description:
      "Lancez un backtest rapide sur données historiques afin de vérifier la robustesse avant un déploiement live.",
    tooltip:
      "Analysez la courbe d'équité, le drawdown et les principaux ratios pour décider d'un passage en production.",
    videoUrl: "https://www.youtube-nocookie.com/embed/_OBlgSz8sSM",
    videoTitle: "Réaliser un backtest",
  },
];

export const STEP_IDS = STEP_LIBRARY.map((step) => step.id);

export function mergeStepMetadata(steps = []) {
  if (!Array.isArray(steps) || !steps.length) {
    return STEP_LIBRARY;
  }
  const dictionary = new Map(STEP_LIBRARY.map((step) => [step.id, step]));
  return steps
    .map((step) => {
      if (!step || typeof step !== "object") {
        return null;
      }
      const base = dictionary.get(step.id) || {};
      return {
        ...base,
        ...step,
        tooltip: step.tooltip ?? base.tooltip,
        videoUrl: step.videoUrl ?? base.videoUrl,
        videoTitle: step.videoTitle ?? base.videoTitle ?? step.title,
      };
    })
    .filter(Boolean);
}
