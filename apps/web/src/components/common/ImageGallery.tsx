import { t } from "@lingui/core/macro";
export function ImageGallery({url,name}:{url:string;name:string}){return <a href={url} target="_blank" rel="noreferrer"><img className="image-preview" src={url} alt={name||t`Image attachment`}/></a>;}
