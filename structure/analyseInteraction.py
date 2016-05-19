import re
import gzip
import collections
import numpy as np
import numpy.ma as ma
import pandas as pd
from statsmodels.nonparametric.smoothers_lowess import lowess

class maskMatrix(object):
    
    def __init__(self, matrix, regions='', overlap = False):
        # Extract bin names
        if matrix.endswith('.gz'):
            with gzip.open(matrix) as inFile:
                self.binNames = inFile.next().strip().split('\t')
        else:
            with open(matrix) as inFile:
                self.binNames = inFile.next().strip().split('\t')
        # Create bin dataframe
        binDF = pd.DataFrame()
        binDF['chr'], binDF['start'], binDF['end'] = zip(
            *[re.split(':|-', x) for x in self.binNames])
        binDF[['start', 'end']] = binDF[['start', 'end']].astype(int)
        binDF['chr'] = binDF['chr'].astype(str)
        binDF['name'] = self.binNames
        binDF['centre'] = np.mean([binDF['start'], binDF['end']], axis=0)
        self.binDF = binDF
        # Open probability matrix and check it is square
        probMatrix = np.loadtxt(matrix, skiprows = 1)
        if probMatrix.shape[0] != probMatrix.shape[1]:
            raise IOError('Matrix must be square')
        # Create mask matrix and remove low values
        chrArray = np.array(self.binDF['chr'])
        maskMatrix = chrArray != chrArray[:,None]
        lowValues = probMatrix.sum(axis=0) < 0.5
        maskMatrix[lowValues,:] = True
        maskMatrix[:,lowValues] = True
        # Add group data to dataframe
        groups = self.binDF['chr'].copy()
        groups[lowValues] = np.nan
        self.binDF['group'] = groups
        # Create masked probability and distance matrices
        self.probMatrix = ma.masked_array(probMatrix, mask = maskMatrix)
        centreArray = np.array(self.binDF['centre'])
        distMatrix = np.abs(centreArray - centreArray[:,None])
        self.distMatrix = ma.masked_array(distMatrix, mask = maskMatrix)
    
    def upDown(self, array, index):
        ''' Returns distance-paired upstream and downstream arrays.'''
        if index == 0:
            up = ma.masked_array([], mask=np.array([],dtype=bool))
        else:
            up = array[index-1::-1]
        down = array[index+1:]
        return(up, down)
    
    def unmaskedPair(self, a1, a2, maxl):
        ''' Returns indices of unmasked array pairs.'''
        maxl = min(len(a1), len(a2), maxl)
        if maxl == 0:
            return(np.array([]))
        masked = np.logical_or(a1.mask[:maxl], a2.mask[:maxl])
        indices = np.where(masked == False)[0]
        return(indices) 
    
    def binDirection(self, maxl = 10):
        ''' Extract interaction direction data for bins '''
        # Create dataframe to store data
        df = pd.DataFrame(columns = ['self', 'inter', 'up', 'down', 'log2'])
        self.binDF = pd.concat([self.binDF, df], axis=1)
        # Loop through rows of the matrix
        for rowNo, row in enumerate(self.probMatrix):
            # Set none values if bin is entirely masked
            if ma.count(row) == 0:
                continue
            # Else calculate values
            else:
                # Extract up and down arrays
                up, down = self.upDown(row, rowNo)
                # Extract probabilities
                selfProb = row[rowNo].sum()
                if up.count() == 0:
                    upProb = 0
                else:
                    upProb = up.sum()
                if down.count() == 0:
                    downProb = 0
                else:
                    downProb = down.sum()
                interProb = 1 - upProb - downProb - selfProb
                # Extract paired bins for log2 calculations
                indices = self.unmaskedPair(up, down, maxl)
                if len(indices) > 0:
                    # Calculate sum of paired up and down bins
                    upSum = up[indices].sum()
                    downSum = down[indices].sum()
                    # Calculate log2 ratio
                    if upSum == 0:
                        if downSum == 0:
                            log2 = np.nan
                        else:
                            log2 = -np.inf
                    elif downSum == 0:
                        log2 = np.inf
                    else:
                        log2 = np.log2(upSum/downSum)
                else:
                    log2 = np.nan
                # Store results
                self.binDF.loc[rowNo,['self','inter','up','down','log2']] = (
                    selfProb, interProb, upProb, downProb, log2)
    
    def binDistance(self):
        ''' Extract weighted mean interaction distance for bins '''
        # Create dataframe to store data
        df = pd.DataFrame(columns = ['dist'])
        self.binDF = pd.concat([self.binDF, df], axis=1)
        # Loop through rows of the matrix
        for rowNo, row in enumerate(self.distMatrix):
            # Set none values if bin is entirely masked
            if ma.count(row) == 0:
                continue
            # Else calculate values
            else:
                # Calculate distance and store results
                dist = ma.average(row, weights = self.probMatrix[rowNo])
                self.binDF.loc[rowNo,'dist'] = np.uint32(dist)
    
    def combinedDistance(self):
        ''' Extract lowess smooth interaction frequency for dataset '''
        # Extract probabilities
        prob = self.probMatrix[~self.probMatrix.mask]
        dist = self.distMatrix[~self.distMatrix.mask]
        # Return data
        return(np.array([dist, prob]).T)
