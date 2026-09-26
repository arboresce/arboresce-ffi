import { NAME, name, printName } from "arboresce";
import {
  initialize,
  name as browserName,
  printName as browserPrint,
} from "arboresce/browser";

const label: string = NAME;
const value: string = name();
const print: () => void = printName;
const browserValue: () => string = browserName;
const browserPrinter: () => void = browserPrint;
const start: typeof initialize = initialize;

void [label, value, print, browserValue, browserPrinter, start];
