import {readFileSync,writeFileSync} from 'node:fs';
const html=readFileSync('index.html','utf8').replace('/src.jsx','/app.js').replace('</head>','<link rel="stylesheet" href="/app.css"></head>');
writeFileSync('dist/index.html',html);
