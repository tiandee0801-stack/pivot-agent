'use strict';

const dvidsDemoLicense = {
 license: '公共领域（美国）',
 licenseUrl: 'https://www.dvidshub.net/about/copyright',
 notice: 'The appearance of U.S. Department of War (DoW) visual information does not imply or constitute DoW endorsement.',
};

const crossfitDemoLicense = {
 kind: 'animated',
 credit: 'CrossFitOS · 3D 动画',
 license: 'CC BY-SA 4.0',
 licenseUrl: 'https://creativecommons.org/licenses/by-sa/4.0/',
 notice: '3D 人体模型由 Z-Anatomy（CC BY-SA 4.0）基于 BodyParts3D（CC BY 4.0）制作。Pivot 转码并从原片提取封面。',
};

function originalCourtDemo(id) {
 return {
  kind: 'original-animation',
  src: `/assets/demos/${id}.mp4`,
  poster: `/assets/demos/${id}.jpg`,
  credit: 'Pivot 换场 · 自制',
  notice: '动作示意 · 待体能教练审核',
 };
}

const catalogDemoAssets = Object.freeze({
 squat: {
  ...dvidsDemoLicense,
  src: '/assets/demos/squat.mp4',
  poster: '/assets/demos/squat.jpg',
  sourceUrl: 'https://www.dvidshub.net/video/517502/body-weight-squat',
  credit: '美国海军陆战队 · Amber Jennings',
 },
 pushup: {
  ...dvidsDemoLicense,
  src: '/assets/demos/pushup.mp4',
  poster: '/assets/demos/pushup.jpg',
  sourceUrl: 'https://www.dvidshub.net/video/283728/push-up-demonstration',
  credit: '美国海军 · Andrea Perez',
 },
 side_plank: {
  ...dvidsDemoLicense,
  src: '/assets/demos/side_plank.mp4',
  poster: '/assets/demos/side_plank.jpg',
  sourceUrl: 'https://www.dvidshub.net/video/640254/side-plank',
  credit: '美国海军陆战队 · Matthew Holfinger',
 },
 lateral_lunge: {
  ...dvidsDemoLicense,
  src: '/assets/demos/lateral_lunge.mp4',
  poster: '/assets/demos/lateral_lunge.jpg',
  sourceUrl: 'https://www.dvidshub.net/video/677362/lateral-lunge',
  credit: '美国海军陆战队 · Matthew Holfinger',
 },
 reverse_lunge: {
  ...dvidsDemoLicense,
  src: '/assets/demos/reverse_lunge.mp4',
  poster: '/assets/demos/reverse_lunge.jpg',
  sourceUrl: 'https://www.dvidshub.net/video/551833/stationary-reverse-lunge',
  credit: '美国海军陆战队 · Matthew Holfinger',
 },
 barbell_back_squat: {
  ...dvidsDemoLicense,
  src: '/assets/demos/barbell_back_squat.mp4',
  poster: '/assets/demos/barbell_back_squat.jpg',
  sourceUrl: 'https://www.dvidshub.net/video/517475/barbell-back-squat',
  credit: '美国海军陆战队 · Amber Jennings',
 },
 bicep_curl: {
  ...dvidsDemoLicense,
  src: '/assets/demos/bicep_curl.mp4',
  poster: '/assets/demos/bicep_curl.jpg',
  sourceUrl: 'https://www.dvidshub.net/video/636923/dumbbell-curl',
  credit: '美国海军陆战队 · Matthew Holfinger',
 },
 plank: {
  ...dvidsDemoLicense,
  src: '/assets/demos/plank.mp4',
  poster: '/assets/demos/plank.jpg',
  sourceUrl: 'https://www.dvidshub.net/video/825280/forearm-plank',
  credit: '美国空军 · Randall Moose',
 },
 dumbbell_rdl: {
  ...dvidsDemoLicense,
  src: '/assets/demos/dumbbell_rdl.mp4',
  poster: '/assets/demos/dumbbell_rdl.jpg',
  sourceUrl: 'https://www.dvidshub.net/video/548459/dumbbell-romanian-deadlift',
  credit: '美国海军陆战队 · Matthew Holfinger',
 },
 dumbbell_row: {
  ...dvidsDemoLicense,
  src: '/assets/demos/dumbbell_row.mp4',
  poster: '/assets/demos/dumbbell_row.jpg',
  sourceUrl: 'https://www.dvidshub.net/video/636921/dumbbell-bent-over-rows',
  credit: '美国海军陆战队 · Matthew Holfinger',
 },
 band_row: {
  ...crossfitDemoLicense,
  src: '/assets/demos/band_row.mp4',
  poster: '/assets/demos/band_row.jpg',
  sourceUrl: 'https://crossfitos.com/exercises/band-row',
 },
 band_rdl: {
  ...crossfitDemoLicense,
  src: '/assets/demos/band_rdl.mp4',
  poster: '/assets/demos/band_rdl.jpg',
  sourceUrl: 'https://crossfitos.com/exercises/banded-romanian-deadlift',
 },
 dead_bug: {
  ...crossfitDemoLicense,
  src: '/assets/demos/dead_bug.mp4',
  poster: '/assets/demos/dead_bug.jpg',
  sourceUrl: 'https://crossfitos.com/exercises/dead-bug',
 },
 short_acceleration: originalCourtDemo('short_acceleration'),
 linear_braking: originalCourtDemo('linear_braking'),
 lateral_shuffle_stop: originalCourtDemo('lateral_shuffle_stop'),
 march_in_place: originalCourtDemo('march_in_place'),
 snap_down: originalCourtDemo('snap_down'),
});
