export function applyDirection(locale:string){document.documentElement.lang=locale;document.documentElement.dir=locale==="ar"?"rtl":"ltr";}
export function isolated(value:string){return `\u2068${value}\u2069`;}
