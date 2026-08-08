const Wellness = require('../models/Wellness');

const getWellness = async (req, res, next) => {
  try {
    let wellness = await Wellness.findOne({ user: req.user._id });
    if (!wellness) {
      wellness = await Wellness.create({ user: req.user._id });
    }
    res.json(wellness);
  } catch (error) {
    next(error);
  }
};

const logMood = async (req, res, next) => {
  try {
    const { mood, emoji, note } = req.body;
    let wellness = await Wellness.findOne({ user: req.user._id });

    if (!wellness) {
      wellness = await Wellness.create({ user: req.user._id });
    }

    // Replace today's mood if it already exists (so re-selecting updates it)
    const todayStart = new Date().setHours(0, 0, 0, 0);
    wellness.moods = wellness.moods.filter(m => new Date(m.date).setHours(0, 0, 0, 0) !== todayStart);

    wellness.moods.push({ mood, emoji, note });
    wellness.lastCheckIn = new Date();

    // Update streak
    const lastCheckIn = wellness.lastCheckIn ? new Date(wellness.lastCheckIn).setHours(0, 0, 0, 0) : null;
    if (!lastCheckIn || todayStart - lastCheckIn <= 86400000) {
      wellness.streak += 1;
    } else if (todayStart - lastCheckIn > 172800000) {
      wellness.streak = 1;
    }

    await wellness.save();
    res.json(wellness);
  } catch (error) {
    next(error);
  }
};

const logSleep = async (req, res, next) => {
  try {
    const { hours, quality } = req.body;
    let wellness = await Wellness.findOne({ user: req.user._id });

    if (!wellness) {
      wellness = await Wellness.create({ user: req.user._id });
    }

    const todayStart = new Date().setHours(0, 0, 0, 0);
    wellness.sleep = wellness.sleep.filter(s => new Date(s.date).setHours(0, 0, 0, 0) !== todayStart);
    wellness.sleep.push({ hours: Number(hours), quality: Number(quality) || 3 });
    wellness.lastCheckIn = new Date();
    await wellness.save();
    res.json(wellness);
  } catch (error) {
    next(error);
  }
};

const logWater = async (req, res, next) => {
  try {
    const { glasses } = req.body;
    let wellness = await Wellness.findOne({ user: req.user._id });

    if (!wellness) {
      wellness = await Wellness.create({ user: req.user._id });
    }

    const todayStart = new Date().setHours(0, 0, 0, 0);
    wellness.water = wellness.water.filter(w => new Date(w.date).setHours(0, 0, 0, 0) !== todayStart);
    wellness.water.push({ glasses: Number(glasses) });
    wellness.lastCheckIn = new Date();
    await wellness.save();
    res.json(wellness);
  } catch (error) {
    next(error);
  }
};

const logExercise = async (req, res, next) => {
  try {
    const { type, duration, calories } = req.body;
    let wellness = await Wellness.findOne({ user: req.user._id });

    if (!wellness) {
      wellness = await Wellness.create({ user: req.user._id });
    }

    wellness.exercise.push({
      type: type || 'Other',
      duration: Number(duration) || 0,
      calories: Number(calories) || 0
    });
    wellness.lastCheckIn = new Date();
    await wellness.save();
    res.json(wellness);
  } catch (error) {
    next(error);
  }
};

const logStress = async (req, res, next) => {
  try {
    const { level, triggers } = req.body;
    let wellness = await Wellness.findOne({ user: req.user._id });

    if (!wellness) {
      wellness = await Wellness.create({ user: req.user._id });
    }

    const todayStart = new Date().setHours(0, 0, 0, 0);
    wellness.stressLevels = wellness.stressLevels.filter(s => new Date(s.date).setHours(0, 0, 0, 0) !== todayStart);
    wellness.stressLevels.push({
      level: Math.min(10, Math.max(1, Number(level) || 5)),
      triggers: triggers || []
    });
    wellness.lastCheckIn = new Date();
    await wellness.save();
    res.json(wellness);
  } catch (error) {
    next(error);
  }
};

const logCycle = async (req, res, next) => {
  try {
    const { phase, symptoms, energyLevel } = req.body;
    let wellness = await Wellness.findOne({ user: req.user._id });

    if (!wellness) {
      wellness = await Wellness.create({ user: req.user._id });
    }

    const todayStart = new Date().setHours(0, 0, 0, 0);
    wellness.cycleLog = wellness.cycleLog.filter(c => new Date(c.date).setHours(0, 0, 0, 0) !== todayStart);
    wellness.cycleLog.push({
      phase: phase || 'unknown',
      symptoms: symptoms || [],
      energyLevel: energyLevel ? Number(energyLevel) : undefined
    });
    wellness.lastCheckIn = new Date();
    await wellness.save();
    res.json(wellness);
  } catch (error) {
    next(error);
  }
};

// ─── Habits / Daily Checklist ───────────────────────────────────────────────
const HABIT_DEFS = [
  { key: 'water', label: 'Drink 8 glasses of water', icon: '💧', target: 8 },
  { key: 'sleep', label: '7+ hours of sleep', icon: '🛌', target: 1 },
  { key: 'exercise', label: '30 min exercise', icon: '🏃‍♀️', target: 1 },
  { key: 'meditation', label: '5-min meditation', icon: '🧘', target: 1 },
  { key: 'journal', label: 'Journal entry', icon: '📝', target: 1 },
  { key: 'stretch', label: 'Desk stretches', icon: '🧘‍♀️', target: 1 },
  { key: 'nutrition', label: '3 balanced meals', icon: '🥗', target: 3 },
  { key: 'screenbreak', label: 'Screen breaks', icon: '👀', target: 3 }
];

// Forward declarations for habit computation helpers
function getTodayKey() {
  return new Date().toISOString().split('T')[0];
}

function habitProgressFor(wellness, habitDef) {
  const todayStart = new Date().setHours(0, 0, 0, 0);
  switch (habitDef.key) {
    case 'water': {
      const rec = wellness.water.find(w => new Date(w.date).setHours(0, 0, 0, 0) === todayStart);
      return rec ? Math.min(rec.glasses, habitDef.target) : 0;
    }
    case 'sleep': {
      const rec = wellness.sleep.find(s => new Date(s.date).setHours(0, 0, 0, 0) === todayStart);
      return rec && rec.hours >= 7 ? 1 : 0;
    }
    case 'exercise': {
      const recs = wellness.exercise.filter(e => new Date(e.date).setHours(0, 0, 0, 0) === todayStart);
      return recs.reduce((sum, e) => sum + (e.duration >= 30 ? 1 : e.duration / 30), 0);
    }
    case 'meditation': {
      const recs = wellness.exercise.filter(e => new Date(e.date).setHours(0, 0, 0, 0) === todayStart && /meditat|breath|yoga/i.test(e.type || ''));
      return recs.length > 0 ? 1 : 0;
    }
    case 'journal': {
      const recs = wellness.exercise.filter(e => new Date(e.date).setHours(0, 0, 0, 0) === todayStart && /journal/i.test(e.type || ''));
      return recs.length > 0 ? 1 : 0;
    }
    case 'stretch': {
      const recs = wellness.exercise.filter(e => new Date(e.date).setHours(0, 0, 0, 0) === todayStart && /stretch/i.test(e.type || ''));
      return recs.length > 0 ? 1 : 0;
    }
    case 'nutrition': {
      const recs = wellness.exercise.filter(e => new Date(e.date).setHours(0, 0, 0, 0) === todayStart && /meal|nutrition|food/i.test(e.type || ''));
      return Math.min(recs.length, habitDef.target);
    }
    case 'screenbreak': {
      const recs = wellness.exercise.filter(e => new Date(e.date).setHours(0, 0, 0, 0) === todayStart && /screenbreak|break/i.test(e.type || ''));
      return Math.min(recs.length, habitDef.target);
    }
    default:
      return 0;
  }
}

const getHabits = async (req, res, next) => {
  try {
    let wellness = await Wellness.findOne({ user: req.user._id });
    if (!wellness) {
      wellness = await Wellness.create({ user: req.user._id });
    }

    const habits = HABIT_DEFS.map(def => ({
      key: def.key,
      label: def.label,
      icon: def.icon,
      target: def.target,
      progress: habitProgressFor(wellness, def),
      done: habitProgressFor(wellness, def) >= def.target
    }));

    const doneCount = habits.filter(h => h.done).length;
    res.json({ habits, total: habits.length, done: doneCount, percent: Math.round((doneCount / habits.length) * 100) });
  } catch (error) {
    next(error);
  }
};

const logHabit = async (req, res, next) => {
  try {
    const { key, value } = req.body;
    let wellness = await Wellness.findOne({ user: req.user._id });
    if (!wellness) {
      wellness = await Wellness.create({ user: req.user._id });
    }

    const todayStart = new Date().setHours(0, 0, 0, 0);
    const todayKey = getTodayKey();

    switch (key) {
      case 'water': {
        const glasses = Number(value) || 1;
        const existing = wellness.water.find(w => new Date(w.date).setHours(0, 0, 0, 0) === todayStart);
        if (existing) existing.glasses += glasses;
        else wellness.water.push({ glasses });
        break;
      }
      case 'sleep': {
        const hours = Number(value) || 7;
        wellness.sleep = wellness.sleep.filter(s => new Date(s.date).setHours(0, 0, 0, 0) !== todayStart);
        wellness.sleep.push({ hours, quality: hours >= 7 ? 5 : 3 });
        break;
      }
      case 'exercise': {
        wellness.exercise.push({ type: 'Exercise', duration: Number(value) || 30, date: new Date() });
        break;
      }
      case 'meditation': {
        wellness.exercise.push({ type: 'Meditation', duration: 5, date: new Date() });
        break;
      }
      case 'journal': {
        wellness.exercise.push({ type: 'Journal', duration: 3, date: new Date() });
        break;
      }
      case 'stretch': {
        wellness.exercise.push({ type: 'Stretch', duration: 3, date: new Date() });
        break;
      }
      case 'nutrition': {
        wellness.exercise.push({ type: 'Meal', duration: 0, date: new Date() });
        break;
      }
      case 'screenbreak': {
        wellness.exercise.push({ type: 'ScreenBreak', duration: 2, date: new Date() });
        break;
      }
      default:
        return res.status(400).json({ message: 'Unknown habit key' });
    }

    wellness.lastCheckIn = new Date();
    await wellness.save();
    res.json({ ok: true, habits: await getHabitsForUser(req.user._id) });
  } catch (error) {
    next(error);
  }
};

async function getHabitsForUser(userId) {
  let wellness = await Wellness.findOne({ user: userId });
  if (!wellness) wellness = await Wellness.create({ user: userId });
  const habits = HABIT_DEFS.map(def => ({
    key: def.key,
    label: def.label,
    icon: def.icon,
    target: def.target,
    progress: habitProgressFor(wellness, def),
    done: habitProgressFor(wellness, def) >= def.target
  }));
  const doneCount = habits.filter(h => h.done).length;
  return { habits, total: habits.length, done: doneCount, percent: Math.round((doneCount / habits.length) * 100) };
}

// ─── Wellness Stats / Summary ───────────────────────────────────────────────
const getWellnessStats = async (req, res, next) => {
  try {
    let wellness = await Wellness.findOne({ user: req.user._id });
    if (!wellness) {
      wellness = await Wellness.create({ user: req.user._id });
    }

    const now = new Date();
    const dayMs = 86400000;
    const todayKey = now.toISOString().split('T')[0];

    // Last 7 days mood, sleep, water, stress, exercise
    const last7 = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date(now.getTime() - i * dayMs);
      const dStart = d.setHours(0, 0, 0, 0);
      const mood = wellness.moods.find(m => new Date(m.date).setHours(0, 0, 0, 0) === dStart);
      const sleep = wellness.sleep.find(s => new Date(s.date).setHours(0, 0, 0, 0) === dStart);
      const water = wellness.water.find(w => new Date(w.date).setHours(0, 0, 0, 0) === dStart);
      const stress = wellness.stressLevels.find(s => new Date(s.date).setHours(0, 0, 0, 0) === dStart);
      const exercise = wellness.exercise.filter(e => new Date(e.date).setHours(0, 0, 0, 0) === dStart);
      last7.push({
        date: d.toISOString().split('T')[0],
        day: d.toLocaleDateString('en-US', { weekday: 'short' }),
        mood: mood ? mood.emoji : null,
        moodLabel: mood ? mood.mood : null,
        sleep: sleep ? sleep.hours : null,
        water: water ? water.glasses : null,
        stress: stress ? stress.level : null,
        exerciseMin: exercise.reduce((sum, e) => sum + (e.duration || 0), 0)
      });
    }

    // Averages
    const avgSleep = last7.filter(d => d.sleep !== null).reduce((s, d) => s + d.sleep, 0) / Math.max(1, last7.filter(d => d.sleep !== null).length);
    const avgWater = last7.filter(d => d.water !== null).reduce((s, d) => s + d.water, 0) / Math.max(1, last7.filter(d => d.water !== null).length);
    const avgStress = last7.filter(d => d.stress !== null).reduce((s, d) => s + d.stress, 0) / Math.max(1, last7.filter(d => d.stress !== null).length);
    const totalExerciseMin = last7.reduce((s, d) => s + d.exerciseMin, 0);

    // Mood distribution
    const moodCounts = {};
    last7.forEach(d => { if (d.moodLabel) moodCounts[d.moodLabel] = (moodCounts[d.moodLabel] || 0) + 1; });

    // Stress trend (is it decreasing?)
    const stressValues = last7.filter(d => d.stress !== null).map(d => d.stress);
    let stressTrend = 'stable';
    if (stressValues.length >= 2) {
      const firstHalf = stressValues.slice(0, Math.floor(stressValues.length / 2)).reduce((s, v) => s + v, 0) / Math.floor(stressValues.length / 2);
      const secondHalf = stressValues.slice(Math.floor(stressValues.length / 2)).reduce((s, v) => s + v, 0) / Math.ceil(stressValues.length / 2);
      if (secondHalf < firstHalf - 0.5) stressTrend = 'decreasing';
      else if (secondHalf > firstHalf + 0.5) stressTrend = 'increasing';
    }

    res.json({
      streak: wellness.streak || 0,
      last7,
      averages: {
        sleep: Math.round(avgSleep * 10) / 10,
        water: Math.round(avgWater * 10) / 10,
        stress: Math.round(avgStress * 10) / 10,
        exerciseMin: totalExerciseMin
      },
      moodCounts,
      stressTrend,
      totalLogs: wellness.moods.length + wellness.sleep.length + wellness.water.length + wellness.exercise.length + wellness.stressLevels.length
    });
  } catch (error) {
    next(error);
  }
};

module.exports = { getWellness, logMood, logSleep, logWater, logExercise, logStress, logCycle, getHabits, logHabit, getWellnessStats };
