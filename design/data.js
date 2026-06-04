// Demo content for the "organic blueberries" query — modeled on the live app's output.
window.DEMO = {
  query: "What are the labeling requirements for organic blueberries?",
  strategy: "sequential",
  latencyMs: 9762,
  confidence: { tier: "high", score: 86, retrieval: 91, coverage: 88 },

  plain: [
    { t: "p", lead: true, html: 'Based on the regulatory context, here are the labeling requirements for organic blueberries.' },
    { t: "h2", html: "General organic labeling" },
    { t: "ul", items: [
      { html: 'The term <em>“organic”</em> may only be used on labels of products produced and handled in accordance with the organic regulations.', cite: "7 CFR § 205.300" },
      { html: 'The term <em>“organic”</em> may <strong>not</strong> be used in a product name to modify a nonorganic ingredient.' },
    ]},
    { t: "h2", html: "For packaged organic products" },
    { t: "p", html: "Packaged organic blueberries may display:" },
    { t: "ul", items: [
      { html: 'The term <em>“100 percent organic”</em> or <em>“organic”</em> on the principal display panel and other package panels.' },
      { html: 'For products labeled <em>“organic”</em> (not 100 percent), the percentage of organic ingredients must be displayed.' },
      { html: "The USDA organic seal." },
      { html: "The seal or logo of the certifying agent that certified the operation." },
    ]},
    { t: "p", html: "Information identifying the certifying agent must also appear on the information panel." },
  ],

  legal: [
    { t: "h2", html: "Permissible use of the term “organic”" },
    { t: "p", html: 'The term “organic” is strictly regulated for use on blueberry product labels. The governing provision establishes both the permission and its limit:' },
    { t: "quote", text: "The term, ‘organic,’ may only be used on labels and in labeling of raw or processed agricultural products, including ingredients, that have been produced and handled in accordance with the regulations in this part.", cite: "7 CFR § 205.300(a)" },
    { t: "quote", text: "The term, ‘organic,’ may not be used in a product name to modify a nonorganic ingredient in the product.", cite: "7 CFR § 205.300(a)" },
    { t: "h2", html: "Labeling of packaged organic blueberries" },
    { t: "p", html: 'Packaged organic blueberries meeting the definition of “processed blueberries” — that is, blueberries which have been frozen, dried, pureed, or made into juice — may display the following on package panels:' },
    { t: "quote", text: "Blueberries which have been frozen, dried, pureed, or made into juice.", cite: "7 CFR § 1218.15" },
    { t: "p", html: 'Where products are sold in nonretail containers, additional identification requirements apply under the nonretail container provisions.' },
  ],

  citations: [
    { n: 1, ref: "21 CFR § 145.120", heading: "Canned berries", agency: "Food and Drug Administration", dept: "Department of Health and Human Services", date: "April 9, 2026", titleNum: 21, titleName: "Title 21 — Food & Drugs" },
    { n: 2, ref: "7 CFR § 205.300", heading: "Use of the term, “organic.”", agency: "Agricultural Marketing Service", dept: "Department of Agriculture", date: "April 13, 2026", titleNum: 7, titleName: "Title 7 — Agriculture" },
    { n: 3, ref: "7 CFR § 205.303", heading: "Packaged products labeled “100 percent organic” or “organic.”", agency: "Agricultural Marketing Service", dept: "Department of Agriculture", date: "April 13, 2026", titleNum: 7, titleName: "Title 7 — Agriculture" },
    { n: 4, ref: "7 CFR § 205.307", heading: "Labeling of nonretail containers", agency: "Agricultural Marketing Service", dept: "Department of Agriculture", date: "April 13, 2026", titleNum: 7, titleName: "Title 7 — Agriculture" },
    { n: 5, ref: "7 CFR § 205.308", heading: "Agricultural products in packages labeled “made with organic.”", agency: "Agricultural Marketing Service", dept: "Department of Agriculture", date: "April 13, 2026", titleNum: 7, titleName: "Title 7 — Agriculture" },
    { n: 6, ref: "7 CFR § 1218.15", heading: "Blueberries.", agency: "Agricultural Marketing Service", dept: "Department of Agriculture", date: "April 13, 2026", titleNum: 7, titleName: "Title 7 — Agriculture" },
    { n: 7, ref: "7 CFR § 1218.53", heading: "Exemption procedures", agency: "Agricultural Marketing Service", dept: "Department of Agriculture", date: "April 13, 2026", titleNum: 7, titleName: "Title 7 — Agriculture" },
    { n: 8, ref: "21 CFR § 101.3", heading: "Identity labeling of food in packaged form", agency: "Food and Drug Administration", dept: "Department of Health and Human Services", date: "April 9, 2026", titleNum: 21, titleName: "Title 21 — Food & Drugs" },
  ],

  pipeline: [
    { label: "Classifying your question", sub: "Determining intent and scope", ms: 420 },
    { label: "Searching the Code of Federal Regulations", sub: "Retrieving grounded sections across 8 titles", ms: 5100 },
    { label: "Generating grounded answer", sub: "Synthesizing three registers with verbatim quotes", ms: 4242 },
  ],
};

window.CFR_TITLES = [
  { num: 7, name: "Agriculture" },
  { num: 21, name: "Food & Drugs" },
  { num: 42, name: "Public Health" },
  { num: 10, name: "Energy" },
  { num: 14, name: "Aeronautics & Space" },
  { num: 29, name: "Labor" },
  { num: 40, name: "Environment" },
  { num: 49, name: "Transportation" },
];

window.EXAMPLES = [
  "What are the labeling requirements for organic blueberries?",
  "Does 21 CFR require allergen declarations on packaged foods?",
  "What changed in the definitions of controlled substances?",
  "What are OSHA's fall-protection rules for construction?",
];
