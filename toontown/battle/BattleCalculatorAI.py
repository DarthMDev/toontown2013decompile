# File: t (Python 2.4)

from BattleBase import *
from DistributedBattleAI import *
from toontown.toonbase.ToontownBattleGlobals import *
import random
from toontown.suit import DistributedSuitBaseAI
import SuitBattleGlobals
import BattleExperienceAI
from toontown.toon import NPCToons
from toontown.pets import PetTricks, DistributedPetProxyAI
from direct.showbase.PythonUtil import lerp

class BattleCalculatorAI:
    AccuracyBonuses = [
        0,
        20,
        40,
        60]
    DamageBonuses = [
        0,
        20,
        20,
        20]
    AttackExpPerTrack = [
        0,
        10,
        20,
        30,
        40,
        50,
        60]
    NumRoundsLured = [
        2,
        2,
        3,
        3,
        4,
        4,
        15]
    TRAP_CONFLICT = -2
    APPLY_HEALTH_ADJUSTMENTS = 1
    TOONS_TAKE_NO_DAMAGE = 0
    CAP_HEALS = 1
    CLEAR_SUIT_ATTACKERS = 1
    SUITS_UNLURED_IMMEDIATELY = 1
    CLEAR_MULTIPLE_TRAPS = 0
    KBBONUS_LURED_FLAG = 0
    KBBONUS_TGT_LURED = 1
    notify = DirectNotifyGlobal.directNotify.newCategory('BattleCalculatorAI')
    toonsAlwaysHit = simbase.config.GetBool('toons-always-hit', 0)
    toonsAlwaysMiss = simbase.config.GetBool('toons-always-miss', 0)
    toonsAlways5050 = simbase.config.GetBool('toons-always-5050', 0)
    suitsAlwaysHit = simbase.config.GetBool('suits-always-hit', 0)
    suitsAlwaysMiss = simbase.config.GetBool('suits-always-miss', 0)
    immortalSuits = simbase.config.GetBool('immortal-suits', 0)
    propAndOrganicBonusStack = simbase.config.GetBool('prop-and-organic-bonus-stack', 0)
    
    def __init__(self, battle, tutorialFlag = 0):
        self.battle = battle
        self.SuitAttackers = { }
        self.currentlyLuredSuits = { }
        self.successfulLures = { }
        self.toonAtkOrder = []
        self.toonHPAdjusts = { }
        self.toonSkillPtsGained = { }
        self.traps = { }
        self.npcTraps = { }
        self.suitAtkStats = { }
        self._BattleCalculatorAI__clearBonuses(hp = 1)
        self._BattleCalculatorAI__clearBonuses(hp = 0)
        self.delayedUnlures = []
        self._BattleCalculatorAI__skillCreditMultiplier = 1
        self.tutorialFlag = tutorialFlag
        self.trainTrapTriggered = False

    
    def setSkillCreditMultiplier(self, mult):
        self._BattleCalculatorAI__skillCreditMultiplier = mult

    
    def getSkillCreditMultiplier(self):
        return self._BattleCalculatorAI__skillCreditMultiplier

    
    def cleanup(self):
        self.battle = None

    
    def _BattleCalculatorAI__calcToonAtkHit(self, attackIndex, atkTargets):
        if len(atkTargets) == 0:
            return (0, 0)
        
        if self.tutorialFlag:
            return (1, 95)
        
        if self.toonsAlways5050:
            roll = random.randint(0, 99)
            if roll < 50:
                return (1, 95)
            else:
                return (0, 0)
        
        if self.toonsAlwaysHit:
            return (1, 95)
        elif self.toonsAlwaysMiss:
            return (0, 0)
        
        debug = self.notify.getDebug()
        attack = self.battle.toonAttacks[attackIndex]
        (atkTrack, atkLevel) = self._BattleCalculatorAI__getActualTrackLevel(attack)
        if atkTrack == NPCSOS:
            return (1, 95)
        
        if atkTrack == FIRE:
            return (1, 95)
        
        if atkTrack == TRAP:
            if debug:
                self.notify.debug('Attack is a trap, so it hits regardless')
            
            attack[TOON_ACCBONUS_COL] = 0
            return (1, 100)
        elif atkTrack == DROP and attack[TOON_TRACK_COL] == NPCSOS:
            unluredSuits = 0
            for tgt in atkTargets:
                if not self._BattleCalculatorAI__suitIsLured(tgt.getDoId()):
                    unluredSuits = 1
                    continue
            
            if unluredSuits == 0:
                attack[TOON_ACCBONUS_COL] = 1
                return (0, 0)
            
        elif atkTrack == DROP:
            allLured = True
            for i in range(len(atkTargets)):
                if self._BattleCalculatorAI__suitIsLured(atkTargets[i].getDoId()):
                    continue
                allLured = False
            
            if allLured:
                attack[TOON_ACCBONUS_COL] = 1
                return (0, 0)
            
        elif atkTrack == PETSOS:
            return self._BattleCalculatorAI__calculatePetTrickSuccess(attack)
        
        tgtDef = 0
        numLured = 0
        if atkTrack != HEAL:
            for currTarget in atkTargets:
                thisSuitDef = self._BattleCalculatorAI__targetDefense(currTarget, atkTrack)
                if debug:
                    self.notify.debug('Examining suit def for toon attack: ' + str(thisSuitDef))
                
                tgtDef = min(thisSuitDef, tgtDef)
                if self._BattleCalculatorAI__suitIsLured(currTarget.getDoId()):
                    numLured += 1
                    continue
            
        
        trackExp = self._BattleCalculatorAI__toonTrackExp(attack[TOON_ID_COL], atkTrack)
        for currOtherAtk in self.toonAtkOrder:
            if currOtherAtk != attack[TOON_ID_COL]:
                nextAttack = self.battle.toonAttacks[currOtherAtk]
                nextAtkTrack = self._BattleCalculatorAI__getActualTrack(nextAttack)
                if atkTrack == nextAtkTrack and attack[TOON_TGT_COL] == nextAttack[TOON_TGT_COL]:
                    currTrackExp = self._BattleCalculatorAI__toonTrackExp(nextAttack[TOON_ID_COL], atkTrack)
                    if debug:
                        self.notify.debug('Examining toon track exp bonus: ' + str(currTrackExp))
                    
                    trackExp = max(currTrackExp, trackExp)
                
            attack[TOON_TGT_COL] == nextAttack[TOON_TGT_COL]
        
        if debug:
            if atkTrack == HEAL:
                self.notify.debug('Toon attack is a heal, no target def used')
            else:
                self.notify.debug('Suit defense used for toon attack: ' + str(tgtDef))
            self.notify.debug('Toon track exp bonus used for toon attack: ' + str(trackExp))
        
        if attack[TOON_TRACK_COL] == NPCSOS:
            randChoice = 0
        else:
            randChoice = random.randint(0, 99)
        propAcc = AvPropAccuracy[atkTrack][atkLevel]
        if atkTrack == LURE:
            treebonus = self._BattleCalculatorAI__toonCheckGagBonus(attack[TOON_ID_COL], atkTrack, atkLevel)
            propBonus = self._BattleCalculatorAI__checkPropBonus(atkTrack)
            if self.propAndOrganicBonusStack:
                propAcc = 0
                if treebonus:
                    self.notify.debug('using organic bonus lure accuracy')
                    propAcc += AvLureBonusAccuracy[atkLevel]
                
                if propBonus:
                    self.notify.debug('using prop bonus lure accuracy')
                    propAcc += AvLureBonusAccuracy[atkLevel]
                
            elif treebonus or propBonus:
                self.notify.debug('using oragnic OR prop bonus lure accuracy')
                propAcc = AvLureBonusAccuracy[atkLevel]
            
        
        attackAcc = propAcc + trackExp + tgtDef
        currAtk = self.toonAtkOrder.index(attackIndex)
        if currAtk > 0 and atkTrack != HEAL:
            prevAtkId = self.toonAtkOrder[currAtk - 1]
            prevAttack = self.battle.toonAttacks[prevAtkId]
            prevAtkTrack = self._BattleCalculatorAI__getActualTrack(prevAttack)
            if atkTrack == LURE:
                if not not attackAffectsGroup(atkTrack, atkLevel, attack[TOON_TRACK_COL]) or self.successfulLures.has_key(attack[TOON_TGT_COL]):
                    pass
            lure = attackAffectsGroup(atkTrack, atkLevel, attack[TOON_TRACK_COL])
            if atkTrack == prevAtkTrack:
                if attack[TOON_TGT_COL] == prevAttack[TOON_TGT_COL] or lure:
                    if prevAttack[TOON_ACCBONUS_COL] == 1:
                        if debug:
                            self.notify.debug('DODGE: Toon attack track dodged')
                        
                    elif prevAttack[TOON_ACCBONUS_COL] == 0:
                        if debug:
                            self.notify.debug('HIT: Toon attack track hit')
                        
                    
                    attack[TOON_ACCBONUS_COL] = prevAttack[TOON_ACCBONUS_COL]
                    return (not attack[TOON_ACCBONUS_COL], attackAcc)
                
        
        atkAccResult = attackAcc
        if debug:
            self.notify.debug('setting atkAccResult to %d' % atkAccResult)
        
        acc = attackAcc + self._BattleCalculatorAI__calcToonAccBonus(attackIndex)
        if atkTrack != LURE and atkTrack != HEAL:
            if atkTrack != DROP:
                if numLured == len(atkTargets):
                    if debug:
                        self.notify.debug('all targets are lured, attack hits')
                    
                    attack[TOON_ACCBONUS_COL] = 0
                    return (1, 100)
                else:
                    luredRatio = float(numLured) / float(len(atkTargets))
                    accAdjust = 100 * luredRatio
                    if accAdjust > 0 and debug:
                        self.notify.debug(str(numLured) + ' out of ' + str(len(atkTargets)) + ' targets are lured, so adding ' + str(accAdjust) + ' to attack accuracy')
                    
                    acc += accAdjust
            elif numLured == len(atkTargets):
                if debug:
                    self.notify.debug('all targets are lured, attack misses')
                
                attack[TOON_ACCBONUS_COL] = 0
                return (0, 0)
            
        
        if acc > MaxToonAcc:
            acc = MaxToonAcc
        
        if randChoice < acc:
            if debug:
                self.notify.debug('HIT: Toon attack rolled' + str(randChoice) + 'to hit with an accuracy of' + str(acc))
            
            attack[TOON_ACCBONUS_COL] = 0
        elif debug:
            self.notify.debug('MISS: Toon attack rolled' + str(randChoice) + 'to hit with an accuracy of' + str(acc))
        
        attack[TOON_ACCBONUS_COL] = 1
        return (not attack[TOON_ACCBONUS_COL], atkAccResult)

    
    def _BattleCalculatorAI__toonTrackExp(self, toonId, track):
        toon = self.battle.getToon(toonId)
        if toon != None:
            toonExpLvl = toon.experience.getExpLevel(track)
            exp = self.AttackExpPerTrack[toonExpLvl]
            if track == HEAL:
                exp = exp * 0.5
            
            self.notify.debug('Toon track exp: ' + str(toonExpLvl) + ' and resulting acc bonus: ' + str(exp))
            return exp
        else:
            return 0

    
    def _BattleCalculatorAI__toonCheckGagBonus(self, toonId, track, level):
        toon = self.battle.getToon(toonId)
        if toon != None:
            return toon.checkGagBonus(track, level)
        else:
            return False

    
    def _BattleCalculatorAI__checkPropBonus(self, track):
        result = False
        if self.battle.getInteractivePropTrackBonus() == track:
            result = True
        
        return result

    
    def _BattleCalculatorAI__targetDefense(self, suit, atkTrack):
        if atkTrack == HEAL:
            return 0
        
        suitDef = SuitBattleGlobals.SuitAttributes[suit.dna.name]['def'][suit.getLevel()]
        return -suitDef

    
    def _BattleCalculatorAI__createToonTargetList(self, attackIndex):
        attack = self.battle.toonAttacks[attackIndex]
        (atkTrack, atkLevel) = self._BattleCalculatorAI__getActualTrackLevel(attack)
        targetList = []
        if atkTrack == NPCSOS:
            return targetList
        
        if not attackAffectsGroup(atkTrack, atkLevel, attack[TOON_TRACK_COL]):
            if atkTrack == HEAL:
                target = attack[TOON_TGT_COL]
            else:
                target = self.battle.findSuit(attack[TOON_TGT_COL])
            if target != None:
                targetList.append(target)
            
        elif atkTrack == HEAL or atkTrack == PETSOS:
            if attack[TOON_TRACK_COL] == NPCSOS or atkTrack == PETSOS:
                targetList = self.battle.activeToons
            else:
                for currToon in self.battle.activeToons:
                    if attack[TOON_ID_COL] != currToon:
                        targetList.append(currToon)
                        continue
                
        else:
            targetList = self.battle.activeSuits
        return targetList

    
    def _BattleCalculatorAI__prevAtkTrack(self, attackerId, toon = 1):
        if toon:
            prevAtkIdx = self.toonAtkOrder.index(attackerId) - 1
            if prevAtkIdx >= 0:
                prevAttackerId = self.toonAtkOrder[prevAtkIdx]
                attack = self.battle.toonAttacks[prevAttackerId]
                return self._BattleCalculatorAI__getActualTrack(attack)
            else:
                return NO_ATTACK
        

    
    def getSuitTrapType(self, suitId):
        if self.traps.has_key(suitId):
            if self.traps[suitId][0] == self.TRAP_CONFLICT:
                return NO_TRAP
            else:
                return self.traps[suitId][0]
        else:
            return NO_TRAP

    
    def _BattleCalculatorAI__suitTrapDamage(self, suitId):
        if self.traps.has_key(suitId):
            return self.traps[suitId][2]
        else:
            return 0

    
    def addTrainTrapForJoiningSuit(self, suitId):
        self.notify.debug('addTrainTrapForJoiningSuit suit=%d self.traps=%s' % (suitId, self.traps))
        trapInfoToUse = None
        for trapInfo in self.traps.values():
            if trapInfo[0] == UBER_GAG_LEVEL_INDEX:
                trapInfoToUse = trapInfo
                break
                continue
        
        if trapInfoToUse:
            self.traps[suitId] = trapInfoToUse
        else:
            self.notify.warning('huh we did not find a train trap?')

    
    def _BattleCalculatorAI__addSuitGroupTrap(self, suitId, trapLvl, attackerId, allSuits, npcDamage = 0):
        if npcDamage == 0:
            if self.traps.has_key(suitId):
                if self.traps[suitId][0] == self.TRAP_CONFLICT:
                    pass
                1
                self.traps[suitId][0] = self.TRAP_CONFLICT
                for suit in allSuits:
                    id = suit.doId
                    if self.traps.has_key(id):
                        self.traps[id][0] = self.TRAP_CONFLICT
                        continue
                    self.traps[id] = [
                        self.TRAP_CONFLICT,
                        0,
                        0]
                
            else:
                toon = self.battle.getToon(attackerId)
                organicBonus = toon.checkGagBonus(TRAP, trapLvl)
                propBonus = self._BattleCalculatorAI__checkPropBonus(TRAP)
                damage = getAvPropDamage(TRAP, trapLvl, toon.experience.getExp(TRAP), organicBonus, propBonus, self.propAndOrganicBonusStack)
                if self.itemIsCredit(TRAP, trapLvl):
                    self.traps[suitId] = [
                        trapLvl,
                        attackerId,
                        damage]
                else:
                    self.traps[suitId] = [
                        trapLvl,
                        0,
                        damage]
                self.notify.debug('calling __addLuredSuitsDelayed')
                self._BattleCalculatorAI__addLuredSuitsDelayed(attackerId, targetId = -1, ignoreDamageCheck = True)
        elif self.traps.has_key(suitId):
            if self.traps[suitId][0] == self.TRAP_CONFLICT:
                self.traps[suitId] = [
                    trapLvl,
                    0,
                    npcDamage]
            
        elif not self._BattleCalculatorAI__suitIsLured(suitId):
            self.traps[suitId] = [
                trapLvl,
                0,
                npcDamage]
        

    
    def _BattleCalculatorAI__addSuitTrap(self, suitId, trapLvl, attackerId, npcDamage = 0):
        if npcDamage == 0:
            if self.traps.has_key(suitId):
                if self.traps[suitId][0] == self.TRAP_CONFLICT:
                    pass
                else:
                    self.traps[suitId][0] = self.TRAP_CONFLICT
            else:
                toon = self.battle.getToon(attackerId)
                organicBonus = toon.checkGagBonus(TRAP, trapLvl)
                propBonus = self._BattleCalculatorAI__checkPropBonus(TRAP)
                damage = getAvPropDamage(TRAP, trapLvl, toon.experience.getExp(TRAP), organicBonus, propBonus, self.propAndOrganicBonusStack)
                if self.itemIsCredit(TRAP, trapLvl):
                    self.traps[suitId] = [
                        trapLvl,
                        attackerId,
                        damage]
                else:
                    self.traps[suitId] = [
                        trapLvl,
                        0,
                        damage]
        elif self.traps.has_key(suitId):
            if self.traps[suitId][0] == self.TRAP_CONFLICT:
                self.traps[suitId] = [
                    trapLvl,
                    0,
                    npcDamage]
            
        elif not self._BattleCalculatorAI__suitIsLured(suitId):
            self.traps[suitId] = [
                trapLvl,
                0,
                npcDamage]
        

    
    def _BattleCalculatorAI__removeSuitTrap(self, suitId):
        if self.traps.has_key(suitId):
            del self.traps[suitId]
        

    
    def _BattleCalculatorAI__clearTrapCreator(self, creatorId, suitId = None):
        if suitId == None:
            for currTrap in self.traps.keys():
                if creatorId == self.traps[currTrap][1]:
                    self.traps[currTrap][1] = 0
                    continue
            
        elif self.traps.has_key(suitId):
            self.traps[suitId][1] = 0
        

    
    def _BattleCalculatorAI__trapCreator(self, suitId):
        if self.traps.has_key(suitId):
            return self.traps[suitId][1]
        else:
            return 0

    
    def _BattleCalculatorAI__initTraps(self):
        self.trainTrapTriggered = False
        keysList = self.traps.keys()
        for currTrap in keysList:
            if self.traps[currTrap][0] == self.TRAP_CONFLICT:
                del self.traps[currTrap]
                continue
        

    
    def _BattleCalculatorAI__calcToonAtkHp(self, toonId):
        attack = self.battle.toonAttacks[toonId]
        targetList = self._BattleCalculatorAI__createToonTargetList(toonId)
        (atkHit, atkAcc) = self._BattleCalculatorAI__calcToonAtkHit(toonId, targetList)
        (atkTrack, atkLevel, atkHp) = self._BattleCalculatorAI__getActualTrackLevelHp(attack)
        if not atkHit and atkTrack != HEAL:
            return None
        
        validTargetAvail = 0
        lureDidDamage = 0
        currLureId = -1
        for currTarget in range(len(targetList)):
            attackLevel = -1
            attackTrack = None
            attackDamage = 0
            toonTarget = 0
            targetLured = 0
            if atkTrack == HEAL or atkTrack == PETSOS:
                targetId = targetList[currTarget]
                toonTarget = 1
            else:
                targetId = targetList[currTarget].getDoId()
            if atkTrack == LURE:
                if self.getSuitTrapType(targetId) == NO_TRAP:
                    if self.notify.getDebug():
                        self.notify.debug('Suit lured, but no trap exists')
                    
                    if self.SUITS_UNLURED_IMMEDIATELY:
                        if not self._BattleCalculatorAI__suitIsLured(targetId, prevRound = 1):
                            if not self._BattleCalculatorAI__combatantDead(targetId, toon = toonTarget):
                                validTargetAvail = 1
                            
                            rounds = self.NumRoundsLured[atkLevel]
                            wakeupChance = 100 - atkAcc * 2
                            npcLurer = attack[TOON_TRACK_COL] == NPCSOS
                            currLureId = self._BattleCalculatorAI__addLuredSuitInfo(targetId, -1, rounds, wakeupChance, toonId, atkLevel, lureId = currLureId, npc = npcLurer)
                            if self.notify.getDebug():
                                self.notify.debug('Suit lured for ' + str(rounds) + ' rounds max with ' + str(wakeupChance) + '% chance to wake up each round')
                            
                            targetLured = 1
                        
                    
                else:
                    attackTrack = TRAP
                    if self.traps.has_key(targetId):
                        trapInfo = self.traps[targetId]
                        attackLevel = trapInfo[0]
                    else:
                        attackLevel = NO_TRAP
                    attackDamage = self._BattleCalculatorAI__suitTrapDamage(targetId)
                    trapCreatorId = self._BattleCalculatorAI__trapCreator(targetId)
                    if trapCreatorId > 0:
                        self.notify.debug('Giving trap EXP to toon ' + str(trapCreatorId))
                        self._BattleCalculatorAI__addAttackExp(attack, track = TRAP, level = attackLevel, attackerId = trapCreatorId)
                    
                    self._BattleCalculatorAI__clearTrapCreator(trapCreatorId, targetId)
                    lureDidDamage = 1
                    if self.notify.getDebug():
                        self.notify.debug('Suit lured right onto a trap! (' + str(AvProps[attackTrack][attackLevel]) + ',' + str(attackLevel) + ')')
                    
                    if not self._BattleCalculatorAI__combatantDead(targetId, toon = toonTarget):
                        validTargetAvail = 1
                    
                    targetLured = 1
                if not self.SUITS_UNLURED_IMMEDIATELY:
                    if not self._BattleCalculatorAI__suitIsLured(targetId, prevRound = 1):
                        if not self._BattleCalculatorAI__combatantDead(targetId, toon = toonTarget):
                            validTargetAvail = 1
                        
                        rounds = self.NumRoundsLured[atkLevel]
                        wakeupChance = 100 - atkAcc * 2
                        npcLurer = attack[TOON_TRACK_COL] == NPCSOS
                        currLureId = self._BattleCalculatorAI__addLuredSuitInfo(targetId, -1, rounds, wakeupChance, toonId, atkLevel, lureId = currLureId, npc = npcLurer)
                        if self.notify.getDebug():
                            self.notify.debug('Suit lured for ' + str(rounds) + ' rounds max with ' + str(wakeupChance) + '% chance to wake up each round')
                        
                        targetLured = 1
                    
                    if attackLevel != -1:
                        self._BattleCalculatorAI__addLuredSuitsDelayed(toonId, targetId)
                    
                
                if targetLured:
                    if (not self.successfulLures.has_key(targetId) or self.successfulLures.has_key(targetId)) and self.successfulLures[targetId][1] < atkLevel:
                        self.notify.debug('Adding target ' + str(targetId) + ' to successfulLures list')
                        self.successfulLures[targetId] = [
                            toonId,
                            atkLevel,
                            atkAcc,
                            -1]
                    
                self.successfulLures[targetId][1] < atkLevel
            elif atkTrack == TRAP:
                npcDamage = 0
                if attack[TOON_TRACK_COL] == NPCSOS:
                    npcDamage = atkHp
                
                if self.CLEAR_MULTIPLE_TRAPS:
                    if self.getSuitTrapType(targetId) != NO_TRAP:
                        self._BattleCalculatorAI__clearAttack(toonId)
                        return None
                    
                
                if atkLevel == UBER_GAG_LEVEL_INDEX:
                    self._BattleCalculatorAI__addSuitGroupTrap(targetId, atkLevel, toonId, targetList, npcDamage)
                    if self._BattleCalculatorAI__suitIsLured(targetId):
                        self.notify.debug('Train Trap on lured suit %d, \n indicating with KBBONUS_COL flag' % targetId)
                        tgtPos = self.battle.activeSuits.index(targetList[currTarget])
                        attack[TOON_KBBONUS_COL][tgtPos] = self.KBBONUS_LURED_FLAG
                    
                else:
                    self._BattleCalculatorAI__addSuitTrap(targetId, atkLevel, toonId, npcDamage)
            elif self._BattleCalculatorAI__suitIsLured(targetId) and atkTrack == SOUND:
                self.notify.debug('Sound on lured suit, ' + 'indicating with KBBONUS_COL flag')
                tgtPos = self.battle.activeSuits.index(targetList[currTarget])
                attack[TOON_KBBONUS_COL][tgtPos] = self.KBBONUS_LURED_FLAG
            
            attackLevel = atkLevel
            attackTrack = atkTrack
            toon = self.battle.getToon(toonId)
            if attack[TOON_TRACK_COL] == NPCSOS or lureDidDamage != 1 or attack[TOON_TRACK_COL] == PETSOS:
                attackDamage = atkHp
            elif atkTrack == FIRE:
                suit = self.battle.findSuit(targetId)
                if suit:
                    costToFire = 1
                    abilityToFire = toon.getPinkSlips()
                    numLeft = abilityToFire - costToFire
                    if numLeft < 0:
                        numLeft = 0
                    
                    toon.b_setPinkSlips(numLeft)
                    if costToFire > abilityToFire:
                        simbase.air.writeServerEvent('suspicious', toonId, 'Toon attempting to fire a %s cost cog with %s pinkslips' % (costToFire, abilityToFire))
                        print 'Not enough PinkSlips to fire cog - print a warning here'
                    else:
                        suit.skeleRevives = 0
                        attackDamage = suit.getHP()
                else:
                    attackDamage = 0
                bonus = 0
            else:
                organicBonus = toon.checkGagBonus(attackTrack, attackLevel)
                propBonus = self._BattleCalculatorAI__checkPropBonus(attackTrack)
                attackDamage = getAvPropDamage(attackTrack, attackLevel, toon.experience.getExp(attackTrack), organicBonus, propBonus, self.propAndOrganicBonusStack)
            if not self._BattleCalculatorAI__combatantDead(targetId, toon = toonTarget):
                if self._BattleCalculatorAI__suitIsLured(targetId) and atkTrack == DROP:
                    self.notify.debug('not setting validTargetAvail, since drop on a lured suit')
                else:
                    validTargetAvail = 1
            
            if attackLevel == -1 and not (atkTrack == FIRE):
                result = LURE_SUCCEEDED
            elif atkTrack != TRAP:
                result = attackDamage
                if atkTrack == HEAL:
                    if not self._BattleCalculatorAI__attackHasHit(attack, suit = 0):
                        result = result * 0.20000000000000001
                    
                    if self.notify.getDebug():
                        self.notify.debug('toon does ' + str(result) + ' healing to toon(s)')
                    
                elif self._BattleCalculatorAI__suitIsLured(targetId) and atkTrack == DROP:
                    result = 0
                    self.notify.debug('setting damage to 0, since drop on a lured suit')
                
                if self.notify.getDebug():
                    self.notify.debug('toon does ' + str(result) + ' damage to suit')
                
            else:
                result = 0
            if result != 0 or atkTrack == PETSOS:
                targets = self._BattleCalculatorAI__getToonTargets(attack)
                if targetList[currTarget] not in targets:
                    if self.notify.getDebug():
                        self.notify.debug('Target of toon is not accessible!')
                        continue
                    continue
                
                targetIndex = targets.index(targetList[currTarget])
                if atkTrack == HEAL:
                    result = result / len(targetList)
                    if self.notify.getDebug():
                        self.notify.debug('Splitting heal among ' + str(len(targetList)) + ' targets')
                    
                
                if self.successfulLures.has_key(targetId) and atkTrack == LURE:
                    self.notify.debug('Updating lure damage to ' + str(result))
                    self.successfulLures[targetId][3] = result
                else:
                    attack[TOON_HP_COL][targetIndex] = result
                if result > 0 and atkTrack != HEAL and atkTrack != DROP and atkTrack != PETSOS:
                    attackTrack = LURE
                    lureInfos = self._BattleCalculatorAI__getLuredExpInfo(targetId)
                    for currInfo in lureInfos:
                        if currInfo[3]:
                            self.notify.debug('Giving lure EXP to toon ' + str(currInfo[0]))
                            self._BattleCalculatorAI__addAttackExp(attack, track = attackTrack, level = currInfo[1], attackerId = currInfo[0])
                        
                        self._BattleCalculatorAI__clearLurer(currInfo[0], lureId = currInfo[2])
                    
                
            atkTrack != PETSOS
        
        if lureDidDamage:
            if self.itemIsCredit(atkTrack, atkLevel):
                self.notify.debug('Giving lure EXP to toon ' + str(toonId))
                self._BattleCalculatorAI__addAttackExp(attack)
            
        
        if not validTargetAvail and self._BattleCalculatorAI__prevAtkTrack(toonId) != atkTrack:
            self._BattleCalculatorAI__clearAttack(toonId)
        

    
    def _BattleCalculatorAI__getToonTargets(self, attack):
        track = self._BattleCalculatorAI__getActualTrack(attack)
        if track == HEAL or track == PETSOS:
            return self.battle.activeToons
        else:
            return self.battle.activeSuits

    
    def _BattleCalculatorAI__attackHasHit(self, attack, suit = 0):
        if suit == 1:
            for dmg in attack[SUIT_HP_COL]:
                if dmg > 0:
                    return 1
                    continue
            
            return 0
        else:
            track = self._BattleCalculatorAI__getActualTrack(attack)
            if not attack[TOON_ACCBONUS_COL]:
                pass
            return track != NO_ATTACK

    
    def _BattleCalculatorAI__attackDamage(self, attack, suit = 0):
        if suit:
            for dmg in attack[SUIT_HP_COL]:
                if dmg > 0:
                    return dmg
                    continue
            
            return 0
        else:
            for dmg in attack[TOON_HP_COL]:
                if dmg > 0:
                    return dmg
                    continue
            
            return 0

    
    def _BattleCalculatorAI__attackDamageForTgt(self, attack, tgtPos, suit = 0):
        if suit:
            return attack[SUIT_HP_COL][tgtPos]
        else:
            return attack[TOON_HP_COL][tgtPos]

    
    def _BattleCalculatorAI__calcToonAccBonus(self, attackKey):
        numPrevHits = 0
        attackIdx = self.toonAtkOrder.index(attackKey)
        for currPrevAtk in range(attackIdx - 1, -1, -1):
            attack = self.battle.toonAttacks[attackKey]
            (atkTrack, atkLevel) = self._BattleCalculatorAI__getActualTrackLevel(attack)
            prevAttackKey = self.toonAtkOrder[currPrevAtk]
            prevAttack = self.battle.toonAttacks[prevAttackKey]
            (prvAtkTrack, prvAtkLevel) = self._BattleCalculatorAI__getActualTrackLevel(prevAttack)
            if self._BattleCalculatorAI__attackHasHit(prevAttack):
                if (attackAffectsGroup(prvAtkTrack, prvAtkLevel, prevAttack[TOON_TRACK_COL]) and attackAffectsGroup(atkTrack, atkLevel, attack[TOON_TRACK_COL]) or attack[TOON_TGT_COL] == prevAttack[TOON_TGT_COL]) and atkTrack != prvAtkTrack:
                    numPrevHits += 1
                    continue
        
        if numPrevHits > 0 and self.notify.getDebug():
            self.notify.debug('ACC BONUS: toon attack received accuracy ' + 'bonus of ' + str(self.AccuracyBonuses[numPrevHits]) + ' from previous attack by (' + str(attack[TOON_ID_COL]) + ') which hit')
        
        return self.AccuracyBonuses[numPrevHits]

    
    def _BattleCalculatorAI__applyToonAttackDamages(self, toonId, hpbonus = 0, kbbonus = 0):
        totalDamages = 0
        if not self.APPLY_HEALTH_ADJUSTMENTS:
            return totalDamages
        
        attack = self.battle.toonAttacks[toonId]
        track = self._BattleCalculatorAI__getActualTrack(attack)
        if track != NO_ATTACK and track != SOS and track != TRAP and track != NPCSOS:
            targets = self._BattleCalculatorAI__getToonTargets(attack)
            for position in range(len(targets)):
                if hpbonus:
                    if targets[position] in self._BattleCalculatorAI__createToonTargetList(toonId):
                        damageDone = attack[TOON_HPBONUS_COL]
                    else:
                        damageDone = 0
                elif kbbonus:
                    if targets[position] in self._BattleCalculatorAI__createToonTargetList(toonId):
                        damageDone = attack[TOON_KBBONUS_COL][position]
                    else:
                        damageDone = 0
                else:
                    damageDone = attack[TOON_HP_COL][position]
                if damageDone <= 0 or self.immortalSuits:
                    continue
                
                if track == HEAL or track == PETSOS:
                    currTarget = targets[position]
                    if self.CAP_HEALS:
                        toonHp = self._BattleCalculatorAI__getToonHp(currTarget)
                        toonMaxHp = self._BattleCalculatorAI__getToonMaxHp(currTarget)
                        if toonHp + damageDone > toonMaxHp:
                            damageDone = toonMaxHp - toonHp
                            attack[TOON_HP_COL][position] = damageDone
                        
                    
                    self.toonHPAdjusts[currTarget] += damageDone
                    totalDamages = totalDamages + damageDone
                    continue
                
                currTarget = targets[position]
                currTarget.setHP(currTarget.getHP() - damageDone)
                targetId = currTarget.getDoId()
                if self.notify.getDebug():
                    if hpbonus:
                        self.notify.debug(str(targetId) + ': suit takes ' + str(damageDone) + ' damage from HP-Bonus')
                    elif kbbonus:
                        self.notify.debug(str(targetId) + ': suit takes ' + str(damageDone) + ' damage from KB-Bonus')
                    else:
                        self.notify.debug(str(targetId) + ': suit takes ' + str(damageDone) + ' damage')
                
                totalDamages = totalDamages + damageDone
                if currTarget.getHP() <= 0:
                    if currTarget.getSkeleRevives() >= 1:
                        currTarget.useSkeleRevive()
                        attack[SUIT_REVIVE_COL] = attack[SUIT_REVIVE_COL] | 1 << position
                    else:
                        self.suitLeftBattle(targetId)
                        attack[SUIT_DIED_COL] = attack[SUIT_DIED_COL] | 1 << position
                        if self.notify.getDebug():
                            self.notify.debug('Suit' + str(targetId) + 'bravely expired in combat')
                        
                self.notify.getDebug()
            
        
        return totalDamages

    
    def _BattleCalculatorAI__combatantDead(self, avId, toon):
        if toon:
            if self._BattleCalculatorAI__getToonHp(avId) <= 0:
                return 1
            
        else:
            suit = self.battle.findSuit(avId)
            if suit.getHP() <= 0:
                return 1
            
        return 0

    
    def _BattleCalculatorAI__combatantJustRevived(self, avId):
        suit = self.battle.findSuit(avId)
        if suit.reviveCheckAndClear():
            return 1
        else:
            return 0

    
    def _BattleCalculatorAI__addAttackExp(self, attack, track = -1, level = -1, attackerId = -1):
        trk = -1
        lvl = -1
        id = -1
        if track != -1 and level != -1 and attackerId != -1:
            trk = track
            lvl = level
            id = attackerId
        elif self._BattleCalculatorAI__attackHasHit(attack):
            if self.notify.getDebug():
                self.notify.debug('Attack ' + repr(attack) + ' has hit')
            
            trk = attack[TOON_TRACK_COL]
            lvl = attack[TOON_LVL_COL]
            id = attack[TOON_ID_COL]
        
        if trk != -1 and trk != NPCSOS and trk != PETSOS and lvl != -1 and id != -1:
            expList = self.toonSkillPtsGained.get(id, None)
            if expList == None:
                expList = [
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0]
                self.toonSkillPtsGained[id] = expList
            
            expList[trk] = min(ExperienceCap, expList[trk] + (lvl + 1) * self._BattleCalculatorAI__skillCreditMultiplier)
        

    
    def _BattleCalculatorAI__clearTgtDied(self, tgt, lastAtk, currAtk):
        position = self.battle.activeSuits.index(tgt)
        currAtkTrack = self._BattleCalculatorAI__getActualTrack(currAtk)
        lastAtkTrack = self._BattleCalculatorAI__getActualTrack(lastAtk)
        if currAtkTrack == lastAtkTrack and lastAtk[SUIT_DIED_COL] & 1 << position and self._BattleCalculatorAI__attackHasHit(currAtk, suit = 0):
            if self.notify.getDebug():
                self.notify.debug('Clearing suit died for ' + str(tgt.getDoId()) + ' at position ' + str(position) + ' from toon attack ' + str(lastAtk[TOON_ID_COL]) + ' and setting it for ' + str(currAtk[TOON_ID_COL]))
            
            lastAtk[SUIT_DIED_COL] = lastAtk[SUIT_DIED_COL] ^ 1 << position
            self.suitLeftBattle(tgt.getDoId())
            currAtk[SUIT_DIED_COL] = currAtk[SUIT_DIED_COL] | 1 << position
        

    
    def _BattleCalculatorAI__addDmgToBonuses(self, dmg, attackIndex, hp = 1):
        toonId = self.toonAtkOrder[attackIndex]
        attack = self.battle.toonAttacks[toonId]
        atkTrack = self._BattleCalculatorAI__getActualTrack(attack)
        if atkTrack == HEAL or atkTrack == PETSOS:
            return None
        
        tgts = self._BattleCalculatorAI__createToonTargetList(toonId)
        for currTgt in tgts:
            tgtPos = self.battle.suits.index(currTgt)
            attackerId = self.toonAtkOrder[attackIndex]
            attack = self.battle.toonAttacks[attackerId]
            track = self._BattleCalculatorAI__getActualTrack(attack)
            if hp:
                if self.hpBonuses[tgtPos].has_key(track):
                    self.hpBonuses[tgtPos][track].append([
                        attackIndex,
                        dmg])
                else:
                    self.hpBonuses[tgtPos][track] = [
                        [
                            attackIndex,
                            dmg]]
            self.hpBonuses[tgtPos].has_key(track)
            if self._BattleCalculatorAI__suitIsLured(currTgt.getDoId()):
                if self.kbBonuses[tgtPos].has_key(track):
                    self.kbBonuses[tgtPos][track].append([
                        attackIndex,
                        dmg])
                else:
                    self.kbBonuses[tgtPos][track] = [
                        [
                            attackIndex,
                            dmg]]
            self.kbBonuses[tgtPos].has_key(track)
        

    
    def _BattleCalculatorAI__clearBonuses(self, hp = 1):
        if hp:
            self.hpBonuses = [
                { },
                { },
                { },
                { }]
        else:
            self.kbBonuses = [
                { },
                { },
                { },
                { }]

    
    def _BattleCalculatorAI__bonusExists(self, tgtSuit, hp = 1):
        tgtPos = self.activeSuits.index(tgtSuit)
        if hp:
            bonusLen = len(self.hpBonuses[tgtPos])
        else:
            bonusLen = len(self.kbBonuses[tgtPos])
        if bonusLen > 0:
            return 1
        
        return 0

    
    def _BattleCalculatorAI__processBonuses(self, hp = 1):
        if hp:
            bonusList = self.hpBonuses
            self.notify.debug('Processing hpBonuses: ' + repr(self.hpBonuses))
        else:
            bonusList = self.kbBonuses
            self.notify.debug('Processing kbBonuses: ' + repr(self.kbBonuses))
        tgtPos = 0
        for currTgt in bonusList:
            for currAtkType in currTgt.keys():
                if (len(currTgt[currAtkType]) > 1 or not hp) and len(currTgt[currAtkType]) > 0:
                    totalDmgs = 0
                    for currDmg in currTgt[currAtkType]:
                        totalDmgs += currDmg[1]
                    
                    numDmgs = len(currTgt[currAtkType])
                    attackIdx = currTgt[currAtkType][numDmgs - 1][0]
                    attackerId = self.toonAtkOrder[attackIdx]
                    attack = self.battle.toonAttacks[attackerId]
                    if hp:
                        attack[TOON_HPBONUS_COL] = math.ceil(totalDmgs * self.DamageBonuses[numDmgs - 1] * 0.01)
                        if self.notify.getDebug():
                            self.notify.debug('Applying hp bonus to track ' + str(attack[TOON_TRACK_COL]) + ' of ' + str(attack[TOON_HPBONUS_COL]))
                        
                    elif len(attack[TOON_KBBONUS_COL]) > tgtPos:
                        attack[TOON_KBBONUS_COL][tgtPos] = totalDmgs * 0.5
                        if self.notify.getDebug():
                            self.notify.debug('Applying kb bonus to track ' + str(attack[TOON_TRACK_COL]) + ' of ' + str(attack[TOON_KBBONUS_COL][tgtPos]) + ' to target ' + str(tgtPos))
                        
                    else:
                        self.notify.warning('invalid tgtPos for knock back bonus: %d' % tgtPos)
            
            tgtPos += 1
        
        if hp:
            self._BattleCalculatorAI__clearBonuses()
        else:
            self._BattleCalculatorAI__clearBonuses(hp = 0)

    
    def _BattleCalculatorAI__handleBonus(self, attackIdx, hp = 1):
        attackerId = self.toonAtkOrder[attackIdx]
        attack = self.battle.toonAttacks[attackerId]
        atkDmg = self._BattleCalculatorAI__attackDamage(attack, suit = 0)
        atkTrack = self._BattleCalculatorAI__getActualTrack(attack)
        if atkDmg > 0:
            if hp:
                if atkTrack != LURE:
                    self.notify.debug('Adding dmg of ' + str(atkDmg) + ' to hpBonuses list')
                    self._BattleCalculatorAI__addDmgToBonuses(atkDmg, attackIdx)
                
            elif self._BattleCalculatorAI__knockBackAtk(attackerId, toon = 1):
                self.notify.debug('Adding dmg of ' + str(atkDmg) + ' to kbBonuses list')
                self._BattleCalculatorAI__addDmgToBonuses(atkDmg, attackIdx, hp = 0)
            
        

    
    def _BattleCalculatorAI__clearAttack(self, attackIdx, toon = 1):
        if toon:
            if self.notify.getDebug():
                self.notify.debug('clearing out toon attack for toon ' + str(attackIdx) + '...')
            
            attack = self.battle.toonAttacks[attackIdx]
            self.battle.toonAttacks[attackIdx] = getToonAttack(attackIdx)
            longest = max(len(self.battle.activeToons), len(self.battle.activeSuits))
            taList = self.battle.toonAttacks
            for j in range(longest):
                taList[attackIdx][TOON_HP_COL].append(-1)
                taList[attackIdx][TOON_KBBONUS_COL].append(-1)
            
            if self.notify.getDebug():
                self.notify.debug('toon attack is now ' + repr(self.battle.toonAttacks[attackIdx]))
            
        else:
            self.notify.warning('__clearAttack not implemented for suits!')

    
    def _BattleCalculatorAI__rememberToonAttack(self, suitId, toonId, damage):
        if not self.SuitAttackers.has_key(suitId):
            self.SuitAttackers[suitId] = {
                toonId: damage }
        elif not self.SuitAttackers[suitId].has_key(toonId):
            self.SuitAttackers[suitId][toonId] = damage
        elif self.SuitAttackers[suitId][toonId] <= damage:
            self.SuitAttackers[suitId] = [
                toonId,
                damage]
        

    
    def _BattleCalculatorAI__postProcessToonAttacks(self):
        self.notify.debug('__postProcessToonAttacks()')
        lastTrack = -1
        lastAttacks = []
        self._BattleCalculatorAI__clearBonuses()
        for currToonAttack in self.toonAtkOrder:
            if currToonAttack != -1:
                attack = self.battle.toonAttacks[currToonAttack]
                (atkTrack, atkLevel) = self._BattleCalculatorAI__getActualTrackLevel(attack)
                if atkTrack != HEAL and atkTrack != SOS and atkTrack != NO_ATTACK and atkTrack != NPCSOS and atkTrack != PETSOS:
                    targets = self._BattleCalculatorAI__createToonTargetList(currToonAttack)
                    allTargetsDead = 1
                    for currTgt in targets:
                        damageDone = self._BattleCalculatorAI__attackDamage(attack, suit = 0)
                        if damageDone > 0:
                            self._BattleCalculatorAI__rememberToonAttack(currTgt.getDoId(), attack[TOON_ID_COL], damageDone)
                        
                        if atkTrack == TRAP:
                            if self.traps.has_key(currTgt.doId):
                                trapInfo = self.traps[currTgt.doId]
                                currTgt.battleTrap = trapInfo[0]
                            
                        
                        targetDead = 0
                        if currTgt.getHP() > 0:
                            allTargetsDead = 0
                        else:
                            targetDead = 1
                            if atkTrack != LURE:
                                for currLastAtk in lastAttacks:
                                    self._BattleCalculatorAI__clearTgtDied(currTgt, currLastAtk, attack)
                                
                            
                        tgtId = currTgt.getDoId()
                        if self.successfulLures.has_key(tgtId) and atkTrack == LURE:
                            lureInfo = self.successfulLures[tgtId]
                            self.notify.debug('applying lure data: ' + repr(lureInfo))
                            toonId = lureInfo[0]
                            lureAtk = self.battle.toonAttacks[toonId]
                            tgtPos = self.battle.activeSuits.index(currTgt)
                            if self.traps.has_key(currTgt.doId):
                                trapInfo = self.traps[currTgt.doId]
                                if trapInfo[0] == UBER_GAG_LEVEL_INDEX:
                                    self.notify.debug('train trap triggered for %d' % currTgt.doId)
                                    self.trainTrapTriggered = True
                                
                            
                            self._BattleCalculatorAI__removeSuitTrap(tgtId)
                            lureAtk[TOON_KBBONUS_COL][tgtPos] = self.KBBONUS_TGT_LURED
                            lureAtk[TOON_HP_COL][tgtPos] = lureInfo[3]
                        elif self._BattleCalculatorAI__suitIsLured(tgtId) and atkTrack == DROP:
                            self.notify.debug('Drop on lured suit, ' + 'indicating with KBBONUS_COL ' + 'flag')
                            tgtPos = self.battle.activeSuits.index(currTgt)
                            attack[TOON_KBBONUS_COL][tgtPos] = self.KBBONUS_LURED_FLAG
                        
                        if targetDead and atkTrack != lastTrack:
                            tgtPos = self.battle.activeSuits.index(currTgt)
                            attack[TOON_HP_COL][tgtPos] = 0
                            attack[TOON_KBBONUS_COL][tgtPos] = -1
                            continue
                    
                    if allTargetsDead and atkTrack != lastTrack:
                        if self.notify.getDebug():
                            self.notify.debug('all targets of toon attack ' + str(currToonAttack) + ' are dead')
                        
                        self._BattleCalculatorAI__clearAttack(currToonAttack, toon = 1)
                        attack = self.battle.toonAttacks[currToonAttack]
                        (atkTrack, atkLevel) = self._BattleCalculatorAI__getActualTrackLevel(attack)
                    
                
                damagesDone = self._BattleCalculatorAI__applyToonAttackDamages(currToonAttack)
                self._BattleCalculatorAI__applyToonAttackDamages(currToonAttack, hpbonus = 1)
                if atkTrack != LURE and atkTrack != DROP and atkTrack != SOUND:
                    self._BattleCalculatorAI__applyToonAttackDamages(currToonAttack, kbbonus = 1)
                
                if lastTrack != atkTrack:
                    lastAttacks = []
                    lastTrack = atkTrack
                
                lastAttacks.append(attack)
                if self.itemIsCredit(atkTrack, atkLevel):
                    if atkTrack == TRAP or atkTrack == LURE:
                        pass
                    elif atkTrack == HEAL:
                        if damagesDone != 0:
                            self._BattleCalculatorAI__addAttackExp(attack)
                        
                    else:
                        self._BattleCalculatorAI__addAttackExp(attack)
                
            self.itemIsCredit(atkTrack, atkLevel)
        
        if self.trainTrapTriggered:
            for suit in self.battle.activeSuits:
                suitId = suit.doId
                self._BattleCalculatorAI__removeSuitTrap(suitId)
                suit.battleTrap = NO_TRAP
                self.notify.debug('train trap triggered, removing trap from %d' % suitId)
            
        
        if self.notify.getDebug():
            for currToonAttack in self.toonAtkOrder:
                attack = self.battle.toonAttacks[currToonAttack]
                self.notify.debug('Final Toon attack: ' + str(attack))
            
        

    
    def _BattleCalculatorAI__allTargetsDead(self, attackIdx, toon = 1):
        allTargetsDead = 1
        if toon:
            targets = self._BattleCalculatorAI__createToonTargetList(attackIdx)
            for currTgt in targets:
                if currTgt.getHp() > 0:
                    allTargetsDead = 0
                    break
                    continue
            
        else:
            self.notify.warning('__allTargetsDead: suit ver. not implemented!')
        return allTargetsDead

    
    def _BattleCalculatorAI__clearLuredSuitsByAttack(self, toonId, kbBonusReq = 0, targetId = -1):
        if self.notify.getDebug():
            self.notify.debug('__clearLuredSuitsByAttack')
        
        if targetId != -1 and self._BattleCalculatorAI__suitIsLured(t.getDoId()):
            self._BattleCalculatorAI__removeLured(t.getDoId())
        else:
            tgtList = self._BattleCalculatorAI__createToonTargetList(toonId)
            for t in tgtList:
                if self._BattleCalculatorAI__suitIsLured(t.getDoId()):
                    if not kbBonusReq or self._BattleCalculatorAI__bonusExists(t, hp = 0):
                        self._BattleCalculatorAI__removeLured(t.getDoId())
                        if self.notify.getDebug():
                            self.notify.debug('Suit %d stepping from lured spot' % t.getDoId())
                        
                self.notify.getDebug()
                self.notify.debug('Suit ' + str(t.getDoId()) + ' not found in currently lured suits')
            

    
    def _BattleCalculatorAI__clearLuredSuitsDelayed(self):
        if self.notify.getDebug():
            self.notify.debug('__clearLuredSuitsDelayed')
        
        for t in self.delayedUnlures:
            if self._BattleCalculatorAI__suitIsLured(t):
                self._BattleCalculatorAI__removeLured(t)
                if self.notify.getDebug():
                    self.notify.debug('Suit %d stepping back from lured spot' % t)
                
            self.notify.getDebug()
            self.notify.debug('Suit ' + str(t) + ' not found in currently lured suits')
        
        self.delayedUnlures = []

    
    def _BattleCalculatorAI__addLuredSuitsDelayed(self, toonId, targetId = -1, ignoreDamageCheck = False):
        if self.notify.getDebug():
            self.notify.debug('__addLuredSuitsDelayed')
        
        if targetId != -1:
            self.delayedUnlures.append(targetId)
        else:
            tgtList = self._BattleCalculatorAI__createToonTargetList(toonId)
            for t in tgtList:
                if self._BattleCalculatorAI__suitIsLured(t.getDoId()) and t.getDoId() not in self.delayedUnlures:
                    if self._BattleCalculatorAI__attackDamageForTgt(self.battle.toonAttacks[toonId], self.battle.activeSuits.index(t), suit = 0) > 0 or ignoreDamageCheck:
                        self.delayedUnlures.append(t.getDoId())
                        continue
            

    
    def _BattleCalculatorAI__calculateToonAttacks(self):
        self.notify.debug('__calculateToonAttacks()')
        self._BattleCalculatorAI__clearBonuses(hp = 0)
        currTrack = None
        self.notify.debug('Traps: ' + str(self.traps))
        maxSuitLevel = 0
        for cog in self.battle.activeSuits:
            maxSuitLevel = max(maxSuitLevel, cog.getActualLevel())
        
        self.creditLevel = maxSuitLevel
        for toonId in self.toonAtkOrder:
            if self._BattleCalculatorAI__combatantDead(toonId, toon = 1):
                if self.notify.getDebug():
                    self.notify.debug("Toon %d is dead and can't attack" % toonId)
                    continue
                continue
            
            attack = self.battle.toonAttacks[toonId]
            atkTrack = self._BattleCalculatorAI__getActualTrack(attack)
            if atkTrack != NO_ATTACK and atkTrack != SOS and atkTrack != NPCSOS:
                if self.notify.getDebug():
                    self.notify.debug('Calculating attack for toon: %d' % toonId)
                
                if self.SUITS_UNLURED_IMMEDIATELY:
                    if currTrack and atkTrack != currTrack:
                        self._BattleCalculatorAI__clearLuredSuitsDelayed()
                    
                
                currTrack = atkTrack
                self._BattleCalculatorAI__calcToonAtkHp(toonId)
                attackIdx = self.toonAtkOrder.index(toonId)
                self._BattleCalculatorAI__handleBonus(attackIdx, hp = 0)
                self._BattleCalculatorAI__handleBonus(attackIdx, hp = 1)
                lastAttack = self.toonAtkOrder.index(toonId) >= len(self.toonAtkOrder) - 1
                if self._BattleCalculatorAI__attackHasHit(attack, suit = 0):
                    pass
                unlureAttack = self._BattleCalculatorAI__unlureAtk(toonId, toon = 1)
                if unlureAttack:
                    if lastAttack:
                        self._BattleCalculatorAI__clearLuredSuitsByAttack(toonId)
                    else:
                        self._BattleCalculatorAI__addLuredSuitsDelayed(toonId)
                
                if lastAttack:
                    self._BattleCalculatorAI__clearLuredSuitsDelayed()
                
        
        self._BattleCalculatorAI__processBonuses(hp = 0)
        self._BattleCalculatorAI__processBonuses(hp = 1)
        self._BattleCalculatorAI__postProcessToonAttacks()

    
    def _BattleCalculatorAI__knockBackAtk(self, attackIndex, toon = 1):
        if toon:
            if self.battle.toonAttacks[attackIndex][TOON_TRACK_COL] == THROW or self.battle.toonAttacks[attackIndex][TOON_TRACK_COL] == SQUIRT:
                if self.notify.getDebug():
                    self.notify.debug('attack is a knockback')
                
                return 1
            
        return 0

    
    def _BattleCalculatorAI__unlureAtk(self, attackIndex, toon = 1):
        attack = self.battle.toonAttacks[attackIndex]
        track = self._BattleCalculatorAI__getActualTrack(attack)
        if toon:
            if track == THROW and track == SQUIRT or track == SOUND:
                if self.notify.getDebug():
                    self.notify.debug('attack is an unlure')
                
                return 1
            
        return 0

    
    def _BattleCalculatorAI__calcSuitAtkType(self, attackIndex):
        theSuit = self.battle.activeSuits[attackIndex]
        attacks = SuitBattleGlobals.SuitAttributes[theSuit.dna.name]['attacks']
        atk = SuitBattleGlobals.pickSuitAttack(attacks, theSuit.getLevel())
        return atk

    
    def _BattleCalculatorAI__calcSuitTarget(self, attackIndex):
        attack = self.battle.suitAttacks[attackIndex]
        suitId = attack[SUIT_ID_COL]
        if self.SuitAttackers.has_key(suitId) and random.randint(0, 99) < 75:
            totalDamage = 0
            for currToon in self.SuitAttackers[suitId].keys():
                totalDamage += self.SuitAttackers[suitId][currToon]
            
            dmgs = []
            for currToon in self.SuitAttackers[suitId].keys():
                dmgs.append((self.SuitAttackers[suitId][currToon] / totalDamage) * 100)
            
            dmgIdx = SuitBattleGlobals.pickFromFreqList(dmgs)
            if dmgIdx == None:
                toonId = self._BattleCalculatorAI__pickRandomToon(suitId)
            else:
                toonId = self.SuitAttackers[suitId].keys()[dmgIdx]
            if toonId == -1 or toonId not in self.battle.activeToons:
                return -1
            
            self.notify.debug('Suit attacking back at toon ' + str(toonId))
            return self.battle.activeToons.index(toonId)
        else:
            return self._BattleCalculatorAI__pickRandomToon(suitId)

    
    def _BattleCalculatorAI__pickRandomToon(self, suitId):
        liveToons = []
        for currToon in self.battle.activeToons:
            if not self._BattleCalculatorAI__combatantDead(currToon, toon = 1):
                liveToons.append(self.battle.activeToons.index(currToon))
                continue
        
        if len(liveToons) == 0:
            self.notify.debug('No tgts avail. for suit ' + str(suitId))
            return -1
        
        chosen = random.choice(liveToons)
        self.notify.debug('Suit randomly attacking toon ' + str(self.battle.activeToons[chosen]))
        return chosen

    
    def _BattleCalculatorAI__suitAtkHit(self, attackIndex):
        if self.suitsAlwaysHit:
            return 1
        elif self.suitsAlwaysMiss:
            return 0
        
        theSuit = self.battle.activeSuits[attackIndex]
        atkType = self.battle.suitAttacks[attackIndex][SUIT_ATK_COL]
        atkInfo = SuitBattleGlobals.getSuitAttack(theSuit.dna.name, theSuit.getLevel(), atkType)
        atkAcc = atkInfo['acc']
        suitAcc = SuitBattleGlobals.SuitAttributes[theSuit.dna.name]['acc'][theSuit.getLevel()]
        acc = atkAcc
        randChoice = random.randint(0, 99)
        if self.notify.getDebug():
            self.notify.debug('Suit attack rolled ' + str(randChoice) + ' to hit with an accuracy of ' + str(acc) + ' (attackAcc: ' + str(atkAcc) + ' suitAcc: ' + str(suitAcc) + ')')
        
        if randChoice < acc:
            return 1
        
        return 0

    
    def _BattleCalculatorAI__suitAtkAffectsGroup(self, attack):
        atkType = attack[SUIT_ATK_COL]
        theSuit = self.battle.findSuit(attack[SUIT_ID_COL])
        atkInfo = SuitBattleGlobals.getSuitAttack(theSuit.dna.name, theSuit.getLevel(), atkType)
        return atkInfo['group'] != SuitBattleGlobals.ATK_TGT_SINGLE

    
    def _BattleCalculatorAI__createSuitTargetList(self, attackIndex):
        attack = self.battle.suitAttacks[attackIndex]
        targetList = []
        if attack[SUIT_ATK_COL] == NO_ATTACK:
            self.notify.debug('No attack, no targets')
            return targetList
        
        debug = self.notify.getDebug()
        if not self._BattleCalculatorAI__suitAtkAffectsGroup(attack):
            targetList.append(self.battle.activeToons[attack[SUIT_TGT_COL]])
            if debug:
                self.notify.debug('Suit attack is single target')
            
        elif debug:
            self.notify.debug('Suit attack is group target')
        
        for currToon in self.battle.activeToons:
            if debug:
                self.notify.debug('Suit attack will target toon' + str(currToon))
            
            targetList.append(currToon)
        
        return targetList

    
    def _BattleCalculatorAI__calcSuitAtkHp(self, attackIndex):
        targetList = self._BattleCalculatorAI__createSuitTargetList(attackIndex)
        attack = self.battle.suitAttacks[attackIndex]
        for currTarget in range(len(targetList)):
            toonId = targetList[currTarget]
            toon = self.battle.getToon(toonId)
            result = 0
            if toon and toon.immortalMode:
                result = 1
            elif self.TOONS_TAKE_NO_DAMAGE:
                result = 0
            elif self._BattleCalculatorAI__suitAtkHit(attackIndex):
                atkType = attack[SUIT_ATK_COL]
                theSuit = self.battle.findSuit(attack[SUIT_ID_COL])
                atkInfo = SuitBattleGlobals.getSuitAttack(theSuit.dna.name, theSuit.getLevel(), atkType)
                result = atkInfo['hp']
            
            targetIndex = self.battle.activeToons.index(toonId)
            attack[SUIT_HP_COL][targetIndex] = result
        

    
    def _BattleCalculatorAI__getToonHp(self, toonDoId):
        handle = self.battle.getToon(toonDoId)
        if handle != None and self.toonHPAdjusts.has_key(toonDoId):
            return handle.hp + self.toonHPAdjusts[toonDoId]
        else:
            return 0

    
    def _BattleCalculatorAI__getToonMaxHp(self, toonDoId):
        handle = self.battle.getToon(toonDoId)
        if handle != None:
            return handle.maxHp
        else:
            return 0

    
    def _BattleCalculatorAI__applySuitAttackDamages(self, attackIndex):
        attack = self.battle.suitAttacks[attackIndex]
        if self.APPLY_HEALTH_ADJUSTMENTS:
            for t in self.battle.activeToons:
                position = self.battle.activeToons.index(t)
                if attack[SUIT_HP_COL][position] <= 0:
                    continue
                
                toonHp = self._BattleCalculatorAI__getToonHp(t)
                if toonHp - attack[SUIT_HP_COL][position] <= 0:
                    if self.notify.getDebug():
                        self.notify.debug('Toon %d has died, removing' % t)
                    
                    self.toonLeftBattle(t)
                    attack[TOON_DIED_COL] = attack[TOON_DIED_COL] | 1 << position
                
                if self.notify.getDebug():
                    self.notify.debug('Toon ' + str(t) + ' takes ' + str(attack[SUIT_HP_COL][position]) + ' damage')
                
                self.toonHPAdjusts[t] -= attack[SUIT_HP_COL][position]
                self.notify.debug('Toon ' + str(t) + ' now has ' + str(self._BattleCalculatorAI__getToonHp(t)) + ' health')
            
        

    
    def _BattleCalculatorAI__suitCanAttack(self, suitId):
        if self._BattleCalculatorAI__combatantDead(suitId, toon = 0) and self._BattleCalculatorAI__suitIsLured(suitId) or self._BattleCalculatorAI__combatantJustRevived(suitId):
            return 0
        
        return 1

    
    def _BattleCalculatorAI__updateSuitAtkStat(self, toonId):
        if self.suitAtkStats.has_key(toonId):
            self.suitAtkStats[toonId] += 1
        else:
            self.suitAtkStats[toonId] = 1

    
    def _BattleCalculatorAI__printSuitAtkStats(self):
        self.notify.debug('Suit Atk Stats:')
        for currTgt in self.suitAtkStats.keys():
            if currTgt not in self.battle.activeToons:
                continue
            
            tgtPos = self.battle.activeToons.index(currTgt)
            self.notify.debug(' toon ' + str(currTgt) + ' at position ' + str(tgtPos) + ' was attacked ' + str(self.suitAtkStats[currTgt]) + ' times')
        
        self.notify.debug('\n')

    
    def _BattleCalculatorAI__calculateSuitAttacks(self):
        for i in range(len(self.battle.suitAttacks)):
            if i < len(self.battle.activeSuits):
                suitId = self.battle.activeSuits[i].doId
                self.battle.suitAttacks[i][SUIT_ID_COL] = suitId
                if not self._BattleCalculatorAI__suitCanAttack(suitId):
                    if self.notify.getDebug():
                        self.notify.debug("Suit %d can't attack" % suitId)
                        continue
                    continue
                
                if self.battle.pendingSuits.count(self.battle.activeSuits[i]) > 0 or self.battle.joiningSuits.count(self.battle.activeSuits[i]) > 0:
                    continue
                
                attack = self.battle.suitAttacks[i]
                attack[SUIT_ID_COL] = self.battle.activeSuits[i].doId
                attack[SUIT_ATK_COL] = self._BattleCalculatorAI__calcSuitAtkType(i)
                attack[SUIT_TGT_COL] = self._BattleCalculatorAI__calcSuitTarget(i)
                if attack[SUIT_TGT_COL] == -1:
                    self.battle.suitAttacks[i] = getDefaultSuitAttack()
                    attack = self.battle.suitAttacks[i]
                    self.notify.debug('clearing suit attack, no avail targets')
                
                self._BattleCalculatorAI__calcSuitAtkHp(i)
                if attack[SUIT_ATK_COL] != NO_ATTACK:
                    if self._BattleCalculatorAI__suitAtkAffectsGroup(attack):
                        for currTgt in self.battle.activeToons:
                            self._BattleCalculatorAI__updateSuitAtkStat(currTgt)
                        
                    else:
                        tgtId = self.battle.activeToons[attack[SUIT_TGT_COL]]
                        self._BattleCalculatorAI__updateSuitAtkStat(tgtId)
                
                targets = self._BattleCalculatorAI__createSuitTargetList(i)
                allTargetsDead = 1
                for currTgt in targets:
                    if self._BattleCalculatorAI__getToonHp(currTgt) > 0:
                        allTargetsDead = 0
                        break
                        continue
                
                if allTargetsDead:
                    self.battle.suitAttacks[i] = getDefaultSuitAttack()
                    if self.notify.getDebug():
                        self.notify.debug('clearing suit attack, targets dead')
                        self.notify.debug('suit attack is now ' + repr(self.battle.suitAttacks[i]))
                        self.notify.debug('all attacks: ' + repr(self.battle.suitAttacks))
                    
                    attack = self.battle.suitAttacks[i]
                
                if self._BattleCalculatorAI__attackHasHit(attack, suit = 1):
                    self._BattleCalculatorAI__applySuitAttackDamages(i)
                
                if self.notify.getDebug():
                    self.notify.debug('Suit attack: ' + str(self.battle.suitAttacks[i]))
                
                attack[SUIT_BEFORE_TOONS_COL] = 0
                continue
        

    
    def _BattleCalculatorAI__updateLureTimeouts(self):
        if self.notify.getDebug():
            self.notify.debug('__updateLureTimeouts()')
            self.notify.debug('Lured suits: ' + str(self.currentlyLuredSuits))
        
        noLongerLured = []
        for currLuredSuit in self.currentlyLuredSuits.keys():
            self._BattleCalculatorAI__incLuredCurrRound(currLuredSuit)
            if self._BattleCalculatorAI__luredMaxRoundsReached(currLuredSuit) or self._BattleCalculatorAI__luredWakeupTime(currLuredSuit):
                noLongerLured.append(currLuredSuit)
                continue
        
        for currLuredSuit in noLongerLured:
            self._BattleCalculatorAI__removeLured(currLuredSuit)
        
        if self.notify.getDebug():
            self.notify.debug('Lured suits: ' + str(self.currentlyLuredSuits))
        

    
    def _BattleCalculatorAI__initRound(self):
        if self.CLEAR_SUIT_ATTACKERS:
            self.SuitAttackers = { }
        
        self.toonAtkOrder = []
        attacks = findToonAttack(self.battle.activeToons, self.battle.toonAttacks, PETSOS)
        for atk in attacks:
            self.toonAtkOrder.append(atk[TOON_ID_COL])
        
        attacks = findToonAttack(self.battle.activeToons, self.battle.toonAttacks, FIRE)
        for atk in attacks:
            self.toonAtkOrder.append(atk[TOON_ID_COL])
        
        for track in range(HEAL, DROP + 1):
            attacks = findToonAttack(self.battle.activeToons, self.battle.toonAttacks, track)
            if track == TRAP:
                sortedTraps = []
                for atk in attacks:
                    if atk[TOON_TRACK_COL] == TRAP:
                        sortedTraps.append(atk)
                        continue
                
                for atk in attacks:
                    if atk[TOON_TRACK_COL] == NPCSOS:
                        sortedTraps.append(atk)
                        continue
                
                attacks = sortedTraps
            
            for atk in attacks:
                self.toonAtkOrder.append(atk[TOON_ID_COL])
            
        
        specials = findToonAttack(self.battle.activeToons, self.battle.toonAttacks, NPCSOS)
        toonsHit = 0
        cogsMiss = 0
        for special in specials:
            npc_track = NPCToons.getNPCTrack(special[TOON_TGT_COL])
            if npc_track == NPC_TOONS_HIT:
                BattleCalculatorAI.toonsAlwaysHit = 1
                toonsHit = 1
                continue
            if npc_track == NPC_COGS_MISS:
                BattleCalculatorAI.suitsAlwaysMiss = 1
                cogsMiss = 1
                continue
        
        if self.notify.getDebug():
            self.notify.debug('Toon attack order: ' + str(self.toonAtkOrder))
            self.notify.debug('Active toons: ' + str(self.battle.activeToons))
            self.notify.debug('Toon attacks: ' + str(self.battle.toonAttacks))
            self.notify.debug('Active suits: ' + str(self.battle.activeSuits))
            self.notify.debug('Suit attacks: ' + str(self.battle.suitAttacks))
        
        self.toonHPAdjusts = { }
        for t in self.battle.activeToons:
            self.toonHPAdjusts[t] = 0
        
        self._BattleCalculatorAI__clearBonuses()
        self._BattleCalculatorAI__updateActiveToons()
        self.delayedUnlures = []
        self._BattleCalculatorAI__initTraps()
        self.successfulLures = { }
        return (toonsHit, cogsMiss)

    
    def calculateRound(self):
        longest = max(len(self.battle.activeToons), len(self.battle.activeSuits))
        for t in self.battle.activeToons:
            for j in range(longest):
                self.battle.toonAttacks[t][TOON_HP_COL].append(-1)
                self.battle.toonAttacks[t][TOON_KBBONUS_COL].append(-1)
            
        
        for i in range(4):
            for j in range(len(self.battle.activeToons)):
                self.battle.suitAttacks[i][SUIT_HP_COL].append(-1)
            
        
        (toonsHit, cogsMiss) = self._BattleCalculatorAI__initRound()
        for suit in self.battle.activeSuits:
            if suit.isGenerated():
                suit.b_setHP(suit.getHP())
                continue
        
        for suit in self.battle.activeSuits:
            if not hasattr(suit, 'dna'):
                self.notify.warning('a removed suit is in this battle!')
                return None
                continue
        
        self._BattleCalculatorAI__calculateToonAttacks()
        self._BattleCalculatorAI__updateLureTimeouts()
        self._BattleCalculatorAI__calculateSuitAttacks()
        if toonsHit == 1:
            BattleCalculatorAI.toonsAlwaysHit = 0
        
        if cogsMiss == 1:
            BattleCalculatorAI.suitsAlwaysMiss = 0
        
        if self.notify.getDebug():
            self.notify.debug('Toon skills gained after this round: ' + repr(self.toonSkillPtsGained))
            self._BattleCalculatorAI__printSuitAtkStats()
        

    
    def _BattleCalculatorAI__calculateFiredCogs():
        import pdb as pdb
        pdb.set_trace()

    
    def toonLeftBattle(self, toonId):
        if self.notify.getDebug():
            self.notify.debug('toonLeftBattle()' + str(toonId))
        
        if self.toonSkillPtsGained.has_key(toonId):
            del self.toonSkillPtsGained[toonId]
        
        if self.suitAtkStats.has_key(toonId):
            del self.suitAtkStats[toonId]
        
        if not self.CLEAR_SUIT_ATTACKERS:
            oldSuitIds = []
            for s in self.SuitAttackers.keys():
                if self.SuitAttackers[s].has_key(toonId):
                    del self.SuitAttackers[s][toonId]
                    if len(self.SuitAttackers[s]) == 0:
                        oldSuitIds.append(s)
                    
                len(self.SuitAttackers[s]) == 0
            
            for oldSuitId in oldSuitIds:
                del self.SuitAttackers[oldSuitId]
            
        
        self._BattleCalculatorAI__clearTrapCreator(toonId)
        self._BattleCalculatorAI__clearLurer(toonId)

    
    def suitLeftBattle(self, suitId):
        if self.notify.getDebug():
            self.notify.debug('suitLeftBattle(): ' + str(suitId))
        
        self._BattleCalculatorAI__removeLured(suitId)
        if self.SuitAttackers.has_key(suitId):
            del self.SuitAttackers[suitId]
        
        self._BattleCalculatorAI__removeSuitTrap(suitId)

    
    def _BattleCalculatorAI__updateActiveToons(self):
        if self.notify.getDebug():
            self.notify.debug('updateActiveToons()')
        
        if not self.CLEAR_SUIT_ATTACKERS:
            oldSuitIds = []
            for s in self.SuitAttackers.keys():
                for t in self.SuitAttackers[s].keys():
                    if t not in self.battle.activeToons:
                        del self.SuitAttackers[s][t]
                        if len(self.SuitAttackers[s]) == 0:
                            oldSuitIds.append(s)
                        
                    len(self.SuitAttackers[s]) == 0
                
            
            for oldSuitId in oldSuitIds:
                del self.SuitAttackers[oldSuitId]
            
        
        for trap in self.traps.keys():
            if self.traps[trap][1] not in self.battle.activeToons:
                self.notify.debug('Trap for toon ' + str(self.traps[trap][1]) + ' will no longer give exp')
                self.traps[trap][1] = 0
                continue
        

    
    def getSkillGained(self, toonId, track):
        return BattleExperienceAI.getSkillGained(self.toonSkillPtsGained, toonId, track)

    
    def getLuredSuits(self):
        luredSuits = self.currentlyLuredSuits.keys()
        self.notify.debug('Lured suits reported to battle: ' + repr(luredSuits))
        return luredSuits

    
    def _BattleCalculatorAI__suitIsLured(self, suitId, prevRound = 0):
        inList = self.currentlyLuredSuits.has_key(suitId)
        if prevRound:
            if inList:
                pass
            return self.currentlyLuredSuits[suitId][0] != -1
        
        return inList

    
    def _BattleCalculatorAI__findAvailLureId(self, lurerId):
        luredSuits = self.currentlyLuredSuits.keys()
        lureIds = []
        for currLured in luredSuits:
            lurerInfo = self.currentlyLuredSuits[currLured][3]
            lurers = lurerInfo.keys()
            for currLurer in lurers:
                currId = lurerInfo[currLurer][1]
                if currLurer == lurerId and currId not in lureIds:
                    lureIds.append(currId)
                    continue
            
        
        lureIds.sort()
        currId = 1
        for currLureId in lureIds:
            if currLureId != currId:
                return currId
            
            currId += 1
        
        return currId

    
    def _BattleCalculatorAI__addLuredSuitInfo(self, suitId, currRounds, maxRounds, wakeChance, lurer, lureLvl, lureId = -1, npc = 0):
        if lureId == -1:
            availLureId = self._BattleCalculatorAI__findAvailLureId(lurer)
        else:
            availLureId = lureId
        if npc == 1:
            credit = 0
        else:
            credit = self.itemIsCredit(LURE, lureLvl)
        if self.currentlyLuredSuits.has_key(suitId):
            lureInfo = self.currentlyLuredSuits[suitId]
            if not lureInfo[3].has_key(lurer):
                lureInfo[1] += maxRounds
                if wakeChance < lureInfo[2]:
                    lureInfo[2] = wakeChance
                
                lureInfo[3][lurer] = [
                    lureLvl,
                    availLureId,
                    credit]
            
        else:
            lurerInfo = {
                lurer: [
                    lureLvl,
                    availLureId,
                    credit] }
            self.currentlyLuredSuits[suitId] = [
                currRounds,
                maxRounds,
                wakeChance,
                lurerInfo]
        self.notify.debug('__addLuredSuitInfo: currLuredSuits -> %s' % repr(self.currentlyLuredSuits))
        return availLureId

    
    def _BattleCalculatorAI__getLurers(self, suitId):
        if self._BattleCalculatorAI__suitIsLured(suitId):
            return self.currentlyLuredSuits[suitId][3].keys()
        
        return []

    
    def _BattleCalculatorAI__getLuredExpInfo(self, suitId):
        returnInfo = []
        lurers = self._BattleCalculatorAI__getLurers(suitId)
        if len(lurers) == 0:
            return returnInfo
        
        lurerInfo = self.currentlyLuredSuits[suitId][3]
        for currLurer in lurers:
            returnInfo.append([
                currLurer,
                lurerInfo[currLurer][0],
                lurerInfo[currLurer][1],
                lurerInfo[currLurer][2]])
        
        return returnInfo

    
    def _BattleCalculatorAI__clearLurer(self, lurerId, lureId = -1):
        luredSuits = self.currentlyLuredSuits.keys()
        for currLured in luredSuits:
            lurerInfo = self.currentlyLuredSuits[currLured][3]
            lurers = lurerInfo.keys()
            for currLurer in lurers:
                if currLurer == lurerId:
                    if lureId == -1 or lureId == lurerInfo[currLurer][1]:
                        del lurerInfo[currLurer]
                        continue
            
        

    
    def _BattleCalculatorAI__setLuredMaxRounds(self, suitId, rounds):
        if self._BattleCalculatorAI__suitIsLured(suitId):
            self.currentlyLuredSuits[suitId][1] = rounds
        

    
    def _BattleCalculatorAI__setLuredWakeChance(self, suitId, chance):
        if self._BattleCalculatorAI__suitIsLured(suitId):
            self.currentlyLuredSuits[suitId][2] = chance
        

    
    def _BattleCalculatorAI__incLuredCurrRound(self, suitId):
        if self._BattleCalculatorAI__suitIsLured(suitId):
            self.currentlyLuredSuits[suitId][0] += 1
        

    
    def _BattleCalculatorAI__removeLured(self, suitId):
        if self._BattleCalculatorAI__suitIsLured(suitId):
            del self.currentlyLuredSuits[suitId]
        

    
    def _BattleCalculatorAI__luredMaxRoundsReached(self, suitId):
        if self._BattleCalculatorAI__suitIsLured(suitId):
            pass
        return self.currentlyLuredSuits[suitId][0] >= self.currentlyLuredSuits[suitId][1]

    
    def _BattleCalculatorAI__luredWakeupTime(self, suitId):
        if self._BattleCalculatorAI__suitIsLured(suitId) and self.currentlyLuredSuits[suitId][0] > 0:
            pass
        return random.randint(0, 99) < self.currentlyLuredSuits[suitId][2]

    
    def itemIsCredit(self, track, level):
        if track == PETSOS:
            return 0
        
        return level < self.creditLevel

    
    def _BattleCalculatorAI__getActualTrack(self, toonAttack):
        if toonAttack[TOON_TRACK_COL] == NPCSOS:
            track = NPCToons.getNPCTrack(toonAttack[TOON_TGT_COL])
            if track != None:
                return track
            else:
                self.notify.warning('No NPC with id: %d' % toonAttack[TOON_TGT_COL])
        
        return toonAttack[TOON_TRACK_COL]

    
    def _BattleCalculatorAI__getActualTrackLevel(self, toonAttack):
        if toonAttack[TOON_TRACK_COL] == NPCSOS:
            (track, level, hp) = NPCToons.getNPCTrackLevelHp(toonAttack[TOON_TGT_COL])
            if track != None:
                return (track, level)
            else:
                self.notify.warning('No NPC with id: %d' % toonAttack[TOON_TGT_COL])
        
        return (toonAttack[TOON_TRACK_COL], toonAttack[TOON_LVL_COL])

    
    def _BattleCalculatorAI__getActualTrackLevelHp(self, toonAttack):
        if toonAttack[TOON_TRACK_COL] == NPCSOS:
            (track, level, hp) = NPCToons.getNPCTrackLevelHp(toonAttack[TOON_TGT_COL])
            if track != None:
                return (track, level, hp)
            else:
                self.notify.warning('No NPC with id: %d' % toonAttack[TOON_TGT_COL])
        elif toonAttack[TOON_TRACK_COL] == PETSOS:
            trick = toonAttack[TOON_LVL_COL]
            petProxyId = toonAttack[TOON_TGT_COL]
            trickId = toonAttack[TOON_LVL_COL]
            healRange = PetTricks.TrickHeals[trickId]
            hp = 0
            if simbase.air.doId2do.has_key(petProxyId):
                petProxy = simbase.air.doId2do[petProxyId]
                if trickId < len(petProxy.trickAptitudes):
                    aptitude = petProxy.trickAptitudes[trickId]
                    hp = int(lerp(healRange[0], healRange[1], aptitude))
                
            else:
                self.notify.warning('pet proxy: %d not in doId2do!' % petProxyId)
            return (toonAttack[TOON_TRACK_COL], toonAttack[TOON_LVL_COL], hp)
        
        return (toonAttack[TOON_TRACK_COL], toonAttack[TOON_LVL_COL], 0)

    
    def _BattleCalculatorAI__calculatePetTrickSuccess(self, toonAttack):
        petProxyId = toonAttack[TOON_TGT_COL]
        if not simbase.air.doId2do.has_key(petProxyId):
            self.notify.warning('pet proxy %d not in doId2do!' % petProxyId)
            toonAttack[TOON_ACCBONUS_COL] = 1
            return (0, 0)
        
        petProxy = simbase.air.doId2do[petProxyId]
        trickId = toonAttack[TOON_LVL_COL]
        toonAttack[TOON_ACCBONUS_COL] = petProxy.attemptBattleTrick(trickId)
        if toonAttack[TOON_ACCBONUS_COL] == 1:
            return (0, 0)
        else:
            return (1, 100)


