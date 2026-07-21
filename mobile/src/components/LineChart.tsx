import React from 'react';
import { View } from 'react-native';
import Svg, { Path, Defs, LinearGradient, Stop, Line } from 'react-native-svg';
import { colors } from '../theme';

// Basit çizgi + alan grafiği. data = fiyat dizisi (eskiden yeniye).
export function LineChart({
  data,
  width,
  height = 200,
}: {
  data: number[];
  width: number;
  height?: number;
}) {
  if (data.length < 2) return null;

  const padV = 12;
  const h = height - padV * 2;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const x = (i: number) => (i / (data.length - 1)) * width;
  const y = (v: number) => padV + h - ((v - min) / range) * h;

  const linePath = data
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(2)},${y(v).toFixed(2)}`)
    .join(' ');
  const areaPath = `${linePath} L${width},${height} L0,${height} Z`;

  const up = data[data.length - 1] >= data[0];
  const stroke = up ? colors.green : colors.red;

  return (
    <View>
      <Svg width={width} height={height}>
        <Defs>
          <LinearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={stroke} stopOpacity={0.28} />
            <Stop offset="1" stopColor={stroke} stopOpacity={0} />
          </LinearGradient>
        </Defs>
        {/* orta çizgi (referans) */}
        <Line
          x1={0}
          y1={padV + h / 2}
          x2={width}
          y2={padV + h / 2}
          stroke={colors.border}
          strokeWidth={1}
          strokeDasharray="4 6"
        />
        <Path d={areaPath} fill="url(#grad)" />
        <Path
          d={linePath}
          fill="none"
          stroke={stroke}
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </Svg>
    </View>
  );
}
