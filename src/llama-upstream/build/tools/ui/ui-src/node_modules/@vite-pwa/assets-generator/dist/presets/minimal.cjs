'use strict';

const minimalPreset = {
  transparent: {
    sizes: [64, 192, 512],
    favicons: [[64, "favicon.ico"]]
  },
  maskable: {
    sizes: [512]
  },
  apple: {
    sizes: [180]
  }
};

exports.minimalPreset = minimalPreset;
