# MineOcclude Large-Scale No-Wall Scaling Study

## Bottom line for Nick

The earlier 2–4-independent-trajectory regime was too small to characterize the visible-position measurement path adequately; increasing the independent training scale toward 100 trajectories materially improved it (`DATA_SCALE_LIMITATION_PLAUSIBLE=True`). More data was not the whole answer: mean pooling remained a plausible bottleneck (`MEAN_POOLING_BOTTLENECK_PLAUSIBLE=True`), while token-preserving structure replicated on the fresh study (`TOKEN_PRESERVING_ADVANTAGE_REPLICATED=True`). The replicated token-preserving success was `FULL_TOKEN_GRID`; training-selected `BEST_K_TOKENS` remained useful and passed the target-specific/readiness composites, but did not beat FULL (`BEST_K_ADVANTAGE=False`) and its selection stability remains `Unclear`. FULL is therefore not established as strictly necessary (`FULL_TOKEN_GRID_NEEDED=Unclear`), and the secondary COARSE result is not established as sufficient. The pre-outcome trajectory/profile confound gate passed, and the prospective B=49 whole-trajectory derangement control established target-specific decoding under the frozen composite rule. Fresh-layout generalization remains untested; these are held-out trajectories from six known layouts. The visible-position gate is passed (`VISIBLE_POSITION_MEASUREMENT_PATH_READY_FOR_OCCLUDED_EXPERIMENT=True`), so the roadmap-directed next step is a new, properly controlled hidden/occluded uncertainty experiment, not a reinterpretation of historical U1/U2.

## What was tested

The study used 120 fresh trajectories from six known layouts, with a frozen 102-trajectory training pool and an untouched fixed test of 18 trajectories (three per layout). It evaluated layer 4 at training sizes N=5/15/40/70/100 over 62 frozen subset authorities (20/16/12/8/6 subsets), using fixed-test equal-layout macro per-trajectory held-out R². The primary representations were `GLOBAL_MEAN`, `FULL_TOKEN_GRID`, and training-selected `BEST_K_TOKENS`; `COARSE_2x6` was secondary. The prospective target-specific control used B=49 within-layout no-self-assignment derangements of complete 60-row training target profiles, preserving temporal order and frame alignment while retaining true untouched fixed-test targets.

Layer 4 was historically exploratory-preselected. This study was not a new all-layer confirmatory search.

## Learning-curve answer

The table gives every validated anchor for every representation. “Median/IQR” and “mean/SD” describe the frozen subset distribution; the last column is the P13 whole-trajectory bootstrap 95% interval. Values are copied from `learning_curve_summary.json`, not recomputed here.

| Representation | N | Subsets | Macro R² median | IQR | Mean | SD | Trajectory-bootstrap 95% interval |
|---|---:|---:|---:|---:|---:|---:|---:|
| GLOBAL_MEAN | 5 | 20 | -93.85313649423037 | 25.102924178665546 | -99.39529111293781 | 22.539753949832324 | [-113.997870646123, -85.23124846205802] |
| GLOBAL_MEAN | 15 | 16 | -13.330504253223776 | 30.556826585616186 | -26.081693895229506 | 29.842400122725696 | [-33.158492572810225, -18.898177709235743] |
| GLOBAL_MEAN | 40 | 12 | -0.6143569297271849 | 0.6436696764983334 | -1.8036833255910658 | 2.9001535001128573 | [-2.5115997406250186, -1.051208988832048] |
| GLOBAL_MEAN | 70 | 8 | -0.010619302645775552 | 0.1032537011370637 | -0.017588175161275407 | 0.057163738641412665 | [-0.11207602240837446, 0.07278328112017161] |
| GLOBAL_MEAN | 100 | 6 | 0.14419073339606606 | 0.03757731514884258 | 0.12958873501327065 | 0.02882154592126436 | [0.039089338734493814, 0.21601837191520032] |
| FULL_TOKEN_GRID | 5 | 20 | -111.11894054644894 | 18.6087648749195 | -112.09783706494511 | 18.610691670198023 | [-128.68797264542593, -96.4234066217426] |
| FULL_TOKEN_GRID | 15 | 16 | -18.811735114179545 | 32.79113202262503 | -34.242355969078226 | 43.113530482445974 | [-43.8794419566114, -24.657393186522473] |
| FULL_TOKEN_GRID | 40 | 12 | -0.39071304193460044 | 0.37124605088503126 | -2.886108618201218 | 6.167371036017108 | [-4.298229262123492, -1.3911885871009404] |
| FULL_TOKEN_GRID | 70 | 8 | 0.3220242340104501 | 0.26827434809517225 | 0.3142671561891152 | 0.19486526654592393 | [0.1365221071370114, 0.47895922536074614] |
| FULL_TOKEN_GRID | 100 | 6 | 0.6569081079204435 | 0.0020900673295437544 | 0.6207113021684175 | 0.08965945619954596 | [0.5463846320543183, 0.6774480185825412] |
| BEST_K_TOKENS | 5 | 20 | -116.56347707055735 | 43.638926206884804 | -121.82177409795202 | 26.003865256301285 | [-138.92348441526562, -105.14731550400508] |
| BEST_K_TOKENS | 15 | 16 | -20.02511776687848 | 26.420561544108484 | -34.982916765989124 | 38.7163901208636 | [-43.81124116064397, -26.090711745660936] |
| BEST_K_TOKENS | 40 | 12 | -0.46648789050797007 | 0.3643965510024458 | -2.807291800270764 | 5.57996099095711 | [-4.126154879330054, -1.40688276926458] |
| BEST_K_TOKENS | 70 | 8 | 0.1994328077227523 | 0.43807902021153533 | 0.20437878353431793 | 0.2534733708759325 | [-0.00548405515574362, 0.39491763995631557] |
| BEST_K_TOKENS | 100 | 6 | 0.633027636259816 | 0.07383643743107304 | 0.5860853276984593 | 0.10447620841177259 | [0.49884458436639606, 0.6631790441290644] |
| COARSE_2x6 | 5 | 20 | -108.24770731583314 | 18.381525499366546 | -113.90789377520166 | 26.045880133416194 | [-132.95052391537368, -95.23419634650193] |
| COARSE_2x6 | 15 | 16 | -14.818101976432366 | 25.591687078453713 | -35.15261007891561 | 54.892845373029424 | [-46.137658130510374, -23.927895653713847] |
| COARSE_2x6 | 40 | 12 | -0.18919965681042072 | 0.6091358334565266 | -2.2555585286297797 | 4.960193253783673 | [-3.445992180571244, -0.9821430540420029] |
| COARSE_2x6 | 70 | 8 | 0.37643128025862094 | 0.12217971604964539 | 0.3846391140294071 | 0.11974289646329894 | [0.2919361818448422, 0.4720198896790032] |
| COARSE_2x6 | 100 | 6 | 0.633955357649268 | 0.03525045663076809 | 0.6136271000974217 | 0.038708888805246776 | [0.581221247683803, 0.643795104100209] |

At high N, the N=100 subset medians were 0.14419073339606606 (GLOBAL), 0.6569081079204435 (FULL), 0.633027636259816 (BEST-K), and 0.633955357649268 (COARSE). All four six-chain N=100-minus-N=5 gains were positive, with the following frozen summaries:

| Representation | Complete chains | Gain median | Gain IQR | Gain interval | Spearman ρ versus N |
|---|---:|---:|---:|---:|---:|
| GLOBAL_MEAN | 6 | 91.61961996121909 | 14.304724558875662 | [84.12906454899849, 110.95255809099064] | 0.9999999999999998 |
| FULL_TOKEN_GRID | 6 | 114.23097053902598 | 15.16088703892585 | [103.73808205715137, 125.17498467915483] | 0.9999999999999998 |
| BEST_K_TOKENS | 6 | 116.09953489223722 | 9.483740997440378 | [105.53893424279829, 136.18451919207578] | 0.9999999999999998 |
| COARSE_2x6 | 6 | 113.81742048287873 | 24.373155424920938 | [106.79548497004801, 141.27526994977384] | 0.9999999999999998 |

This is the quantitative basis for `DATA_SCALE_LIMITATION_PLAUSIBLE=True`. The validated learning-curve and subset-dispersion views are [p8_primary_learning_curves.png](p8_primary_learning_curves.png) and [p13_learning_curve_decision.png](p13_learning_curve_decision.png).

### N=5 omitted-layout caveat

N=5 contains five of six layouts, so N=5-to-N=15 cannot be attributed purely to trajectory count. The authority balances which layout is omitted. These are the exact N=5 omitted-layout subset medians and IQRs (count in parentheses):

| Representation | L01 | L02 | L03 | L04 | L05 | L06 |
|---|---:|---:|---:|---:|---:|---:|
| GLOBAL_MEAN | -90.82305786173117 / 9.328291791237191 (4) | -101.40534100949372 / 18.031684177402937 (4) | -90.16931097744572 / 16.272529029226547 (3) | -113.03454848910083 / 9.442009648318702 (3) | -89.7506446065039 / 17.94843960656671 (3) | -75.29650081913326 / 5.576760940907604 (3) |
| FULL_TOKEN_GRID | -96.63865057607521 / 13.916703612010807 (4) | -117.70991609823275 / 13.938377027362122 (4) | -106.80301719087709 / 9.074687217691235 (3) | -129.63682659060817 / 4.863815507066846 (3) | -99.80913617874428 / 9.839667928983076 (3) | -104.4753921343309 / 7.796282215356783 (3) |
| BEST_K_TOKENS | -118.11935106244555 / 17.174931193942484 (4) | -128.05527570645145 / 33.20225047543144 (4) | -98.67075418949919 / 28.79399618241237 (3) | -147.45852124000496 / 17.97939231150184 (3) | -98.30644703194207 / 10.926530660677486 (3) | -104.9930642758111 / 33.99939739701179 (3) |
| COARSE_2x6 | -91.44807280400812 / 19.385659350845785 (4) | -116.2197508501006 / 17.240948580394644 (4) | -109.4585344822912 / 10.852186480106255 (3) | -136.22347891286554 / 20.26773685532099 (3) | -95.81999262449544 / 36.18168750665316 (3) | -106.97674731452769 / 1.4293993538315561 (3) |

## Representation comparison

Each row is a matched-subset difference A−B from `representation_comparison.json`: median, paired interval, and positive-difference wins. These estimates remain descriptive except where the frozen P13 categorical rules explicitly adjudicate them.

| Contrast | N | Median delta | Paired interval | Wins / subsets (rate) |
|---|---:|---:|---:|---:|
| FULL−GLOBAL | 5 | -15.153446553964784 | [-18.16532787962451, -6.974867610650411] | 3/20 (0.15) |
| FULL−GLOBAL | 15 | -4.414857006750177 | [-15.509103581324542, -2.437204894839384] | 4/16 (0.25) |
| FULL−GLOBAL | 40 | 0.2336616229073148 | [-3.182200539612944, 0.3593213154040605] | 10/12 (0.8333333333333334) |
| FULL−GLOBAL | 70 | 0.2737251733764924 | [0.19947014184923179, 0.4655475906769226] | 8/8 (1.0) |
| FULL−GLOBAL | 100 | 0.5094725924590892 | [0.40913920247693686, 0.5480071050420707] | 6/6 (1.0) |
| BEST-K−GLOBAL | 5 | -20.660784711909272 | [-34.000805003221465, -12.001356617352627] | 3/20 (0.15) |
| BEST-K−GLOBAL | 15 | -6.154780887431727 | [-15.103986548840233, -3.3391260053071683] | 4/16 (0.25) |
| BEST-K−GLOBAL | 40 | 0.15104749851779653 | [-2.71759009340734, 0.204519201259162] | 8/12 (0.6666666666666666) |
| BEST-K−GLOBAL | 70 | 0.2077971670459115 | [0.048161897157377336, 0.38930979805380206] | 6/8 (0.75) |
| BEST-K−GLOBAL | 100 | 0.5065648636224394 | [0.36279164654272383, 0.5263597436169086] | 6/6 (1.0) |
| BEST-K−FULL | 5 | -0.6134117839337989 | [-18.008160409401412, -2.2647288484491885] | 10/20 (0.5) |
| BEST-K−FULL | 15 | 2.142734872023322 | [-6.141925735614039, 4.760933502078526] | 10/16 (0.625) |
| BEST-K−FULL | 40 | -0.13810519274952654 | [-0.24297113214897673, 0.4544770624849508] | 4/12 (0.3333333333333333) |
| BEST-K−FULL | 70 | -0.08342999657451808 | [-0.2234568220603293, -0.030331555247407795] | 1/8 (0.125) |
| BEST-K−FULL | 100 | -0.024022062364545294 | [-0.06578954772451279, -0.009909395859642345] | 1/6 (0.16666666666666666) |
| COARSE−GLOBAL | 5 | -9.896173922501738 | [-24.411008042216906, -5.5730518311787804] | 5/20 (0.25) |
| COARSE−GLOBAL | 15 | 0.2247191340116932 | [-23.62350127547676, 1.7487804843763373] | 9/16 (0.5625) |
| COARSE−GLOBAL | 40 | 0.35210780864134616 | [-1.7709557608052706, 0.48311227344386043] | 10/12 (0.8333333333333334) |
| COARSE−GLOBAL | 70 | 0.40387018988039175 | [0.3217008524742541, 0.48374042401262995] | 8/8 (1.0) |
| COARSE−GLOBAL | 100 | 0.4886655881478046 | [0.444409174013003, 0.5222833498702751] | 6/6 (1.0) |
| FULL−COARSE | 5 | -2.150284911790905 | [-3.9567022140829806, 8.56266907736832] | 8/20 (0.4) |
| FULL−COARSE | 15 | -2.764124531218621 | [-4.990178470581967, 8.460495781113686] | 3/16 (0.1875) |
| FULL−COARSE | 40 | -0.14228340656285238 | [-1.387603853839774, -0.08480487869916097] | 2/12 (0.16666666666666666) |
| FULL−COARSE | 70 | -0.013686791110169932 | [-0.1505298676178491, 0.0029351560569576274] | 4/8 (0.5) |
| FULL−COARSE | 100 | 0.02235727958611705 | [-0.04429376328641509, 0.044265919304234604] | 5/6 (0.8333333333333334) |
| BEST-K−COARSE | 5 | -3.920022354639066 | [-19.644078606715688, 3.6480691766928146] | 8/20 (0.4) |
| BEST-K−COARSE | 15 | -1.5694194927685206 | [-9.501961569157485, 11.306711571267785] | 6/16 (0.375) |
| BEST-K−COARSE | 40 | -0.2983636034772741 | [-0.9583771469432926, -0.21672191302096683] | 2/12 (0.16666666666666666) |
| BEST-K−COARSE | 70 | -0.07714953787504494 | [-0.33177020991472705, -0.047972218807207076] | 1/8 (0.125) |
| BEST-K−COARSE | 100 | -0.0009365850954510813 | [-0.09280153819419801, 0.028864458601949434] | 3/6 (0.5) |

The frozen categorical result is that FULL, not BEST-K, supplied the replicated token-preserving component: `FULL_TOKEN_GRID=True`, `BEST_K_TOKENS=False`, and `BEST_K_ADVANTAGE=False`. The best observed core was FULL. COARSE is secondary and `COARSE_SPATIAL_READOUT_SUFFICIENT=Unclear`; it cannot be promoted to a sufficiency claim. See [p13_representation_comparison_decision.png](p13_representation_comparison_decision.png).

## BEST-K selection and stability

BEST-K ranking, K selection, and alpha selection were training-only within each subset. The selected K counts were:

| N | Selected K counts |
|---:|---|
| 5 | K=1: 5; K=4: 1; K=8: 3; K=32: 1; K=128: 10 |
| 15 | K=1: 10; K=4: 1; K=8: 2; K=16: 1; K=64: 1; K=128: 1 |
| 40 | K=1: 1; K=4: 1; K=16: 1; K=128: 9 |
| 70 | K=16: 3; K=32: 1; K=128: 4 |
| 100 | K=8: 1; K=32: 1; K=64: 1; K=128: 3 |

Pairwise token-selection stability was weak at small N and stronger descriptively at large N:

| N | Pair count | Median Jaccard | Median chance-adjusted/Kuncheva | Median rank Spearman |
|---:|---:|---:|---:|---:|
| 5 | 190 | 0.0078125 | -0.024390243902439025 | 0.008081940867936704 |
| 15 | 120 | 0.0 | -0.0029850746268656712 | 0.10921130886474792 |
| 40 | 66 | 0.2864321608040201 | 0.6529447115384616 | 0.7634829772291573 |
| 70 | 28 | 0.1550925925925926 | 0.8801081730769231 | 0.9137790804350441 |
| 100 | 15 | 0.25 | 1.0 | 0.982419504849639 |

The P9 descriptive label was `STABLE_AT_LARGE_N`, but the frozen roadmap supplied no numeric confirmatory stability threshold. P13 therefore correctly retains `BEST_K_TOKEN_SELECTION_STABLE=Unclear`. These results do not establish causal token localization, attention, or saliency. Validated visualizations are [token_selection_frequency.png](token_selection_frequency.png) and [token_stability_vs_n.png](token_stability_vs_n.png).

## Target-specific null

The B=49 control was prospective and is distinct from the historical B=100 context. Within each layout it used a no-self-assignment derangement of complete training target profiles. Temporal order and row/frame alignment within the donor profile were preserved; fixed-test targets stayed true and untouched. Each replicate refit the authorized training-only state. The frozen upper-tail rule was `(1 + count(null >= observed)) / (49 + 1)`, and the 95th-percentile statistic was the 47th nearest-rank order statistic.

| Representation | Observed statistic | Empirical q95 | Add-one p | Positive layouts | Separates own null |
|---|---:|---:|---:|---:|---|
| GLOBAL_MEAN | 0.15128414212699445 | -73.7307101276475 | 0.02 | 4/6 | True |
| FULL_TOKEN_GRID | 0.6586437442101604 | -130.4709852704585 | 0.02 | 6/6 | True |
| BEST_K_TOKENS | 0.5536849680151364 | -81.08669636140074 | 0.02 | 5/6 | True |
| COARSE_2x6 | 0.6454811092837313 | -112.94761154743696 | 0.02 | 6/6 | True |

All four observed statistics separate their own null. The frozen target-specific composite, however, counts CORE representations only and also requires at least 5/6 positive layouts. FULL and BEST-K qualify. GLOBAL separates its null but fails the layout qualification at 4/6; COARSE is not a CORE representation for this composite. Therefore `TARGET_SPECIFIC_DECODING_ESTABLISHED=True`. The full 49-value arrays remain in the canonical runtime authority and are deliberately not reproduced here. See [p13_null_layout_profile_decision.png](p13_null_layout_profile_decision.png).

## Layout/profile evidence

The canonical P11 per-layout R² values show the sign pattern used by the frozen composites:

| Representation | L01 | L02 | L03 | L04 | L05 | L06 | Positive |
|---|---:|---:|---:|---:|---:|---:|---:|
| GLOBAL_MEAN | 0.5697981505015033 | 0.4122872172694228 | 0.46686781816850703 | 0.7063144087989225 | -0.8192806359817676 | -0.42828210599462135 | 4/6 |
| FULL_TOKEN_GRID | 0.8119234939441062 | 0.6974872376390758 | 0.6892254139059085 | 0.8888419739248622 | 0.4035517370924069 | 0.46083260875460264 | 6/6 |
| BEST_K_TOKENS | 0.8463357828938142 | 0.6794847707395367 | 0.7392523403889478 | 0.8640765457576397 | 0.29997109018360246 | -0.10701072187272231 | 5/6 |
| COARSE_2x6 | 0.8025705941543695 | 0.707113982609267 | 0.6349058875169699 | 0.8528075384885959 | 0.3907210831986328 | 0.48476756973455276 | 6/6 |

The profile-family table below reports the exact median held-out R² by N in the order N=5 / 15 / 40 / 70 / 100. The full count, IQR, mean, SD, minimum, and maximum fields remain in `learning_curve_summary.json`.

| Representation | Profile family | Median R² at N=5 / 15 / 40 / 70 / 100 |
|---|---|---|
| GLOBAL_MEAN | ASYMMETRIC_RESTART | -103.77074715967859 / -9.884988127877357 / -0.9400824625326685 / -0.5168490646037617 / -0.3509430111280205 |
| GLOBAL_MEAN | DELAYED_BOUNDED_BURST | -35.353953940713204 / -6.5407158993575205 / -0.06663690387748718 / 0.34840720011252385 / 0.5002148313028656 |
| GLOBAL_MEAN | LONG_DWELL_RESTART | -95.30195372481889 / -6.2978720311375245 / -0.3042379313977835 / 0.05200304085477858 / 0.24539125892963537 |
| GLOBAL_MEAN | MULTI_DWELL_PULSE | -187.9648578735838 / -31.76637415487012 / -0.8615626746785339 / 0.12423236165948238 / 0.2087404438683754 |
| GLOBAL_MEAN | TERMINAL_HOLD_RESTART | -89.9618344238605 / -5.237580312434894 / -0.6283333165279358 / 0.009057049984337411 / 0.20054838198334846 |
| FULL_TOKEN_GRID | ASYMMETRIC_RESTART | -122.04227854826328 / -5.086739405702296 / 0.2786806901186017 / 0.437933002248195 / 0.5933309042889138 |
| FULL_TOKEN_GRID | DELAYED_BOUNDED_BURST | -49.390899031192404 / -7.420447701045399 / -1.2145481840006602 / -0.2003823968132924 / 0.7400827155348162 |
| FULL_TOKEN_GRID | LONG_DWELL_RESTART | -146.2296564289643 / -1.255554388412567 / 0.5044979886454201 / 0.747045484253863 / 0.7909489579540664 |
| FULL_TOKEN_GRID | MULTI_DWELL_PULSE | -207.0086488078461 / -29.68234051513002 / 0.056951065072196716 / 0.537550683943223 / 0.6021830835201337 |
| FULL_TOKEN_GRID | TERMINAL_HOLD_RESTART | -106.30263560136024 / -3.9997727334580837 / -0.7172569735468628 / 0.41855291383304 / 0.5940779204706681 |
| BEST_K_TOKENS | ASYMMETRIC_RESTART | -128.417276473932 / -16.53073762639223 / 0.019973659547065606 / 0.1832231413556797 / 0.497541085263978 |
| BEST_K_TOKENS | DELAYED_BOUNDED_BURST | -51.84750960174797 / -12.319254827440988 / -1.459345054549185 / -0.3502318180573829 / 0.7903825116387067 |
| BEST_K_TOKENS | LONG_DWELL_RESTART | -139.47953824593867 / -5.259765795001012 / 0.4166268486953675 / 0.6326398765090533 / 0.7197502594992229 |
| BEST_K_TOKENS | MULTI_DWELL_PULSE | -262.0731690831026 / -18.218224983771943 / -0.02563317393414799 / 0.597992294031416 / 0.6451245475880227 |
| BEST_K_TOKENS | TERMINAL_HOLD_RESTART | -108.5966750359429 / -12.796605894375027 / -1.2781768699875156 / 0.4948540718847912 / 0.5760320587045171 |
| COARSE_2x6 | ASYMMETRIC_RESTART | -109.19534892632817 / -3.8927147219032143 / 0.0707513672826403 / 0.37564678112021294 / 0.5919291417766601 |
| COARSE_2x6 | DELAYED_BOUNDED_BURST | -40.64035420200294 / -5.931919603558325 / -0.6808808112766672 / 0.17110542318406957 / 0.6855515606806029 |
| COARSE_2x6 | LONG_DWELL_RESTART | -150.96460684181642 / -1.6951599164203008 / 0.4201917440121276 / 0.5640351232183405 / 0.710995744998006 |
| COARSE_2x6 | MULTI_DWELL_PULSE | -208.58752578282594 / -18.561980509376994 / 0.08168151684680125 / 0.5055141994675614 / 0.6199145728515622 |
| COARSE_2x6 | TERMINAL_HOLD_RESTART | -108.14386975796904 / -2.367950114678657 / 0.04500274504980303 / 0.4674380034718064 / 0.5820719244873098 |

The pre-outcome confound gate passed all frozen component checks, including exact 120-trajectory membership, six-layout balance, profile/reporting-stratum balance, direction and shape-class balance, motion compliance, visibility/no-wall authority, and the frozen time-position/profile-similarity gates. Thus `TRAJECTORY_PROFILE_CONFOUND_CONTROLLED=True`.

This evidence concerns held-out trajectories from the same six known layouts. P12 is `DEFERRED_BY_DESIGN`; P13 records primary-study layout generalization as `NOT_ADJUDICATED_IN_PRIMARY_STUDY` and historical context as `MIXED`. It does not establish fresh-layout generalization.

## Final adjudication

| Frozen P13 field | Adjudication |
|---|---|
| DATA_SCALE_LIMITATION_PLAUSIBLE | True |
| MEAN_POOLING_BOTTLENECK_PLAUSIBLE | True |
| TOKEN_PRESERVING_ADVANTAGE_REPLICATED | True (`FULL_TOKEN_GRID=True`; `BEST_K_TOKENS=False`) |
| BEST_K_ADVANTAGE | False |
| BEST_K_TOKEN_SELECTION_STABLE | Unclear |
| FULL_TOKEN_GRID_NEEDED | Unclear |
| COARSE_SPATIAL_READOUT_SUFFICIENT | Unclear |
| TRAJECTORY_PROFILE_CONFOUND_CONTROLLED | True |
| TARGET_SPECIFIC_DECODING_ESTABLISHED | True |
| LAYOUT_GENERALIZATION | primary study: `NOT_ADJUDICATED_IN_PRIMARY_STUDY`; P12: `DEFERRED_BY_DESIGN`; historical context: `MIXED` |
| VISIBLE_POSITION_MEASUREMENT_PATH_READY_FOR_OCCLUDED_EXPERIMENT | True |

Readiness by representation was GLOBAL false (4/6 positive layouts), FULL true (6/6), BEST-K true (P13 readiness summary: 6/6), and COARSE true (6/6). The target-specific composite separately records BEST-K at 5/6 and qualifies FULL and BEST-K as CORE representations; these are different frozen composites and are not interchangeable.

## What this does NOT establish

- No fresh-layout generalization: the fixed test contains fresh trajectories from six known layouts.
- No causal token localization and no attention/saliency claim.
- No proof that FULL is strictly necessary, and no proof that COARSE is sufficient.
- No retrospective rewrite of the original frozen MVP.
- No retrospective reinterpretation or rescue of historical U1/U2.
- No new all-layer confirmatory search; layer 4 remains exploratory-preselected.

## Next direction

`RETURN_TO_HIDDEN_OCCLUDED_UNCERTAINTY_EXPERIMENT`

The visible positive-control measurement path has now passed the frozen readiness gate, including the prospective target-specific control. The next experiment should therefore prospectively test persistence, updating, and uncertainty under occlusion instead of repeating visible-data scaling. It must be a new properly controlled occluded study and must not retroactively reinterpret the frozen historical U1/U2 experiment.
