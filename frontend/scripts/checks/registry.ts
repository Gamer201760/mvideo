import { consistency } from "./rules/code/consistency.ts"
import { fileLength } from "./rules/code/fileLength.ts"
import { iconAlias } from "./rules/code/iconAlias.ts"
import { importCycles } from "./rules/code/importCycles.ts"
import { layers } from "./rules/code/layers.ts"
import { noMocks } from "./rules/code/mocks.ts"
import { noComments } from "./rules/code/noComments.ts"
import { packageSize, packageSubject } from "./rules/code/packageShape.ts"
import { pageTitles } from "./rules/code/pageTitles.ts"
import { remoteAssets } from "./rules/code/remoteAssets.ts"
import { rawRequests } from "./rules/code/requests.ts"
import { motionLibraries, uiKits } from "./rules/code/stack.ts"
import { cssDuplicates } from "./rules/css/cssDuplicates.ts"
import { cssModules, globalStyles } from "./rules/css/cssStructure.ts"
import { cssLiterals, cssTokenRefs, cssTransitions } from "./rules/css/cssValues.ts"
import { noGradients } from "./rules/css/decor.ts"
import { hoverGate } from "./rules/css/hoverGate.ts"
import { pageWidth } from "./rules/css/pageWidth.ts"
import { scaleTokens, tokenLayers } from "./rules/css/scale.ts"
import { noSideStripe } from "./rules/css/sideStripe.ts"
import { contrast, themeParity } from "./rules/css/themeTokens.ts"
import { touchTargets } from "./rules/css/touchTargets.ts"
import { motionTokens } from "./rules/motion/motionTokens.ts"
import { tsTimings } from "./rules/motion/tsTimings.ts"
import { noEmoji, symbolGlyphs, textSeparators } from "./rules/text/separators.ts"
import { cyrillic, jsxText } from "./rules/text/texts.ts"
import type { Check } from "./types.ts"

export const CHECKS: readonly Check[] = [
  fileLength,
  noComments,
  packageSize,
  packageSubject,
  importCycles,
  layers,
  rawRequests,
  noMocks,
  pageTitles,
  motionLibraries,
  uiKits,
  remoteAssets,
  iconAlias,
  consistency,
  cyrillic,
  jsxText,
  textSeparators,
  symbolGlyphs,
  noEmoji,
  cssLiterals,
  cssTokenRefs,
  cssModules,
  globalStyles,
  cssDuplicates,
  cssTransitions,
  scaleTokens,
  tokenLayers,
  themeParity,
  contrast,
  noSideStripe,
  noGradients,
  pageWidth,
  touchTargets,
  hoverGate,
  motionTokens,
  tsTimings,
]
