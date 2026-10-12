const number = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });
export const formatNumber = (value: number) => number.format(value);
