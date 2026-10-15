const fs = require('fs');
const mongoose = require('mongoose');
const config = require('../config');
const Analysis = require('../models/Analysis');

let mongoReady = false;
const memory = new Map();

async function init() {
  if (!config.MONGODB_URI) return;
  try {
    await mongoose.connect(config.MONGODB_URI, { serverSelectionTimeoutMS: 5000 });
    mongoReady = true;
    // eslint-disable-next-line no-console
    console.log('MongoDB connected: persistent history enabled.');
  } catch (err) {
    mongoReady = false;
    // eslint-disable-next-line no-console
    console.warn('MongoDB unavailable, using in-memory history:', err.message);
  }
}

function isPersistent() {
  return mongoReady;
}

function toPublic(doc) {
  const o = doc && doc.toObject ? doc.toObject() : doc;
  return {
    id: o.analysisId,
    filename: o.filename,
    fileSize: o.fileSize,
    task: o.task,
    predictedLabel: o.predictedLabel,
    probabilities: o.probabilities,
    modelVersion: o.modelVersion,
    packetCount: o.packetCount,
    featureSampleCount: o.featureSampleCount,
    processingTimeSeconds: o.processingTimeSeconds,
    warnings: o.warnings || [],
    charts: o.charts,
    status: o.status || 'completed',
    createdAt: o.createdAt,
  };
}

async function save(record) {
  const entry = { ...record, createdAt: new Date().toISOString() };
  if (mongoReady) {
    try {
      const doc = await Analysis.create({
        analysisId: entry.id,
        filename: entry.filename,
        fileSize: entry.fileSize,
        task: entry.task,
        predictedLabel: entry.predictedLabel,
        probabilities: entry.probabilities,
        modelVersion: entry.modelVersion,
        packetCount: entry.packetCount,
        featureSampleCount: entry.featureSampleCount,
        processingTimeSeconds: entry.processingTimeSeconds,
        warnings: entry.warnings,
        charts: entry.charts,
        status: 'completed',
      });
      return { record: toPublic(doc), persisted: true };
    } catch (err) {
      memory.set(entry.id, entry);
      return { record: entry, persisted: false, persistError: 'Analysis completed, but history could not be saved.' };
    }
  }
  memory.set(entry.id, entry);
  return { record: entry, persisted: false };
}

async function list() {
  if (mongoReady) {
    try {
      const docs = await Analysis.find({}).sort({ createdAt: -1 }).limit(100);
      return { items: docs.map(toPublic), persistent: true };
    } catch (err) {
      return { items: [...memory.values()].reverse(), persistent: false };
    }
  }
  return { items: [...memory.values()].reverse(), persistent: false };
}

async function getById(id) {
  if (mongoReady) {
    try {
      const doc = await Analysis.findOne({ analysisId: id });
      if (doc) return { record: toPublic(doc), persistent: true };
    } catch (err) {
      // fall through to memory
    }
  }
  const rec = memory.get(id);
  return rec ? { record: rec, persistent: false } : null;
}

module.exports = { init, isPersistent, save, list, getById };
