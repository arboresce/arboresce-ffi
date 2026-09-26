import {
  name as nativeName,
  printName as nativePrintName,
} from "../native/native.cjs";

export const NAME: string = nativeName();
export const name = nativeName;
export const printName = nativePrintName;
