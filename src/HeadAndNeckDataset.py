import os
import unicodecsv as csv
from torch.utils.data import Dataset
import SimpleITK as sitk
import torch
import numpy as np
import Utils
from eval.LandmarkHandler import PointReader
import Options

class HeadAndNeckDataset(Dataset):
    """Face Landmarks dataset."""

    def __init__(self, csv_file, transform=None, loadOnInstantiation=True, smoothFilter=None):

        self.transform = transform
        self.smooth = smoothFilter
        self.loadOnInstantiation = loadOnInstantiation
        csvtrainingFiles =  open(csv_file, 'rb')
        self.meansAndStds = {}
        self.spacings = {}
        self.origins = {}
        self.directionCosines = {}
        try:        
          trianingCSVFileReader = csv.reader(csvtrainingFiles, delimiter=';', encoding='iso8859_15')
          if (self.loadOnInstantiation):
            self.loadedIgSamples = {}
          
          self.dataFileList = []
          self.labelFileList = []
          self.maskFileList = []
          self.landMarkFileList = []
          
          idx = 0
          for trainingFilePath in trianingCSVFileReader:
            imgFiles = []
            maskFiles = []
            landMarkFiles = []
            labelFiles = []
            i = 0
            while (True):
              trainingFileName = trainingFilePath[0] + os.path.sep +'img' + str(i) + '.nii.gz'
              if (os.path.isfile(trainingFileName)):
                imgFiles.append(trainingFileName)
              else:
                trainingFileName = trainingFilePath[0] + os.path.sep +'img' + str(i) + '.nrrd'
                if (os.path.isfile(trainingFileName)):
                  imgFiles.append(trainingFileName)
                else:
                  break
                
              maskFileName = trainingFilePath[0] + os.path.sep + 'mask' + str(i) + '.nii.gz'
              if (os.path.isfile(maskFileName)):
                maskFiles.append(maskFileName)
              maskFileName = trainingFilePath[0] + os.path.sep + 'mask' + str(i) + '.nrrd'
              if (os.path.isfile(maskFileName)):
                maskFiles.append(maskFileName)
              
              landmarkFileName = trainingFilePath[0] + os.path.sep + str(i) + '0.pts'
              if (os.path.isfile(landmarkFileName)):
                landMarkFiles.append(landmarkFileName)
              
              labelsFileName = trainingFilePath[0] + os.path.sep + 'struct' + str(i) + '.nii.gz'  
              if (os.path.isfile(labelsFileName)):
                labelFiles.append(labelsFileName)
              labelsFileName = trainingFilePath[0] + os.path.sep + 'struct' + str(i) + '.nrrd'  
              if (os.path.isfile(labelsFileName)):
                labelFiles.append(labelsFileName)
              i=i+1
            
            self.dataFileList.append(imgFiles)
            self.labelFileList.append(labelFiles)
            self.maskFileList.append(maskFiles)
            self.landMarkFileList.append(landMarkFiles)
            
            self.channels = len(imgFiles)
            if (self.loadOnInstantiation):
              sample = self.loadData(idx)
              self.loadedIgSamples[idx] = sample
              idx = idx + 1

          
          self.length = len(self.dataFileList)
        finally:
          csvtrainingFiles.close()

    def __len__(self):
        return self.length
    
    def getChannels(self):
      return self.channels;
    
    def loadData(self, idx):
      imgData = []
      spacing = []
      imgSize = []
      trainingFileNames = self.dataFileList[idx]
      maskFileNames = self.maskFileList[idx]
      labelsFileNames = self.labelFileList[idx]
      landMarkFileNames = self.landMarkFileList[idx]
      
      for trainingFileName in trainingFileNames:
        #https://na-mic.org/w/images/a/a7/SimpleITK_with_Slicer_HansJohnson.pdf
        tmp = sitk.ReadImage(str(trainingFileName))
        imgNii = sitk.GetArrayFromImage(tmp)
        curSpacing = tmp.GetSpacing()
        currImgSize = tmp.GetSize()
        if (len(spacing)):
          if(curSpacing != spacing):
            print('Error: input images do not have same voxel spacing.')
        else:
          spacing = curSpacing
          
        if (len(imgSize)):
          if(currImgSize != imgSize):
            print('Error: input images do not have same size.')
        else:
          imgSize = currImgSize
          
        imgData.append(imgNii)
        
        ## we process the image in the form the form z,y,x but meta data comes as x,y,z
        self.spacings[idx] = spacing
        self.origins[idx] = tmp.GetOrigin()
        self.directionCosines[idx] = tmp.GetDirection()
        
      imgData = np.stack(imgData).astype('float32')
      
#       imgData[imgData < -1000] = -1000
#       imgData[imgData > 100] = 100
      
      labelData = []
      if (len(trainingFileNames) == len(labelsFileNames)):
        for labelsFileName in labelsFileNames:
          tmp = sitk.ReadImage(str(labelsFileName))
          labelsNii = sitk.GetArrayFromImage(tmp)
          labelData.append(labelsNii)
        labelData = np.stack(labelData)
      
      maskData = []
      if (len(trainingFileNames) == len(maskFileNames)):
        for maskFileName in maskFileNames:
          tmp = sitk.ReadImage(str(maskFileName))
          maskNii = sitk.GetArrayFromImage(tmp)
          maskData.append(maskNii)
        maskData = np.stack(maskData)
        
        imgMean = imgData[maskData > 0].mean()
        imgData = imgData - imgMean
        imgStd = imgData[maskData > 0].std()
        imgData = imgData / imgStd
        imgData[maskData == 0] = 0
        self.meansAndStds[idx] = (imgMean, imgStd)
        
      else:
        imgMean = imgData.mean()
        imgData = imgData - imgMean
        imgStd = imgData.std()
        imgData = imgData / imgStd
        self.meansAndStds[idx] = (imgMean, imgStd)
      
      imgData, maskData, labelData = self.getRightSizedData(imgData, maskData, labelData, idx)
      
      landmarkData = []
      if (len(trainingFileNames) == len(landMarkFileNames)):
        pr = PointReader()
        for lmFileName in landMarkFileNames:
          points = pr.loadData(lmFileName)
          landmarkData.append(points)
      
      sample = {'image': imgData, 'label': labelData, 'mask': maskData, 'landmarks': landmarkData}
      if self.transform:
        sample = self.transform(sample)
      if self.smooth:
        sample = self.smooth(sample)
      return sample  
    
    
    def getSpacing(self, idx):
      return self.spacings[idx]
    
    def getSpacingXZFlip(self, idx):
      return (self.spacings[idx][2],self.spacings[idx][1],self.spacings[idx][0])

    def getOrigin(self, idx):
      return self.origins[idx]
    
    def getOriginXZFlip(self, idx):
      return (self.origins[idx][2],self.origins[idx][1],self.origins[idx][0])
    
    def getDirectionCosines(self, idx):
      return self.directionCosines[idx]
    
    def getRightSizedData(self, imgData, maskData, labelData, idx):
      
      nuOfDownSampleLayers = Options.netDepth - 1
      nuOfDownSampleSteps = len(Options.downSampleRates) -1
      timesDividableByTwo = 2**(nuOfDownSampleLayers + nuOfDownSampleSteps)
      
      if len(maskData) > 0:
        maskChanSum = np.sum(maskData,0)
        minMaxXYZ = np.nonzero(maskChanSum)
        min0 = minMaxXYZ[0].min()
        max0 = minMaxXYZ[0].max() + 1
        
        min1 = minMaxXYZ[1].min()
        max1 = minMaxXYZ[1].max() + 1
        
        min2 = minMaxXYZ[2].min()
        max2 = minMaxXYZ[2].max() + 1
        
        min0, max0 = self.getMinMax(min0, max0, maskData.shape[1], timesDividableByTwo)
        min1, max1 = self.getMinMax(min1, max1, maskData.shape[2], timesDividableByTwo)
        min2, max2 = self.getMinMax(min2, max2, maskData.shape[3], timesDividableByTwo)
        
        maskData = maskData[:,min0:max0, min1:max1, min2:max2]
        imgData = imgData[:,min0:max0, min1:max1, min2:max2]
        
        #self.origins[idx] = tuple(self.origins[idx] + np.asarray([min0, min1, min2]) *  self.spacings[idx])
        self.origins[idx] = tuple(self.origins[idx] + np.asarray([min2, min1, min0]) *  self.spacings[idx])
        
        if len(labelData) > 0:
          labelData = labelData[:,min0:max0, min1:max1, min2:max2]
      
      else: 
        imgData = imgData[:,:int((imgData.shape[1]/timesDividableByTwo)*timesDividableByTwo),:int(imgData.shape[2]/timesDividableByTwo)*timesDividableByTwo,:int(imgData.shape[3]/timesDividableByTwo)*timesDividableByTwo]   
        
        if len(labelData) > 0:
          labelData = labelData[:,:int(labelData.shape[1]/timesDividableByTwo)*timesDividableByTwo,:int(labelData.shape[2]/timesDividableByTwo)*timesDividableByTwo,:int(labelData.shape[3]/timesDividableByTwo)*timesDividableByTwo]
          
      return imgData, maskData, labelData
    
    def getMinMax(self, minVal, maxVal, maxLength, timesDividableByTwo):
      l = maxVal - minVal
      if l % timesDividableByTwo == 0:
        return minVal, maxVal
      else:
        lNew = (int(l/timesDividableByTwo)+1)*timesDividableByTwo
        if lNew > maxLength:
          minVal = 0
          maxVal = int((maxLength)/timesDividableByTwo)*timesDividableByTwo
        else:
          lDiff = lNew - l
          lDiffHalf = int(lDiff/2)
          if minVal - lDiffHalf > 0 and maxVal + (lDiff - lDiffHalf) < maxLength:
            minVal = minVal - lDiffHalf
            maxVal = maxVal + (lDiff - lDiffHalf)
          elif minVal - lDiff > 0:
            minVal = minVal - lDiff
          elif maxVal + lDiff <= maxLength:
            maxVal = maxVal + lDiff
          else:
            minVal = 0
            maxVal = int((maxLength)/timesDividableByTwo)*timesDividableByTwo
        
        return minVal, maxVal  
            
          
      
    def __getitem__(self, idx):
        
        ##works currently only for single thread
        if self.loadOnInstantiation:
          sample = self.loadedIgSamples[idx]
        else:
          sample = self.loadData(idx)

        return sample

    def saveData(self, data, path,  filename, idx = -1, meanSubtract = True):
      if idx > -1:
        if (data.GetPixelIDValue() < 12 and meanSubtract):
          (imgMean, imgStd) = self.meansAndStds[idx]
          data = data * imgStd
          data = data + imgMean
        data.SetSpacing( self.getSpacing(idx) )
        data.SetOrigin( self.getOrigin(idx) )
        data.SetDirection(self.directionCosines[idx])
      if not os.path.isdir(path):
        os.makedirs(path)
      sitk.WriteImage(data, path + os.path.sep + filename)

class ToTensor(object):
    """Convert ndarrays in sample to Tensors."""

    def __call__(self, sample):
        image, label, mask, landmarkData = sample['image'], sample['label'], sample['mask'], sample['landmarks']

        labelTorch = torch.tensor([1])
        if(len(label) > 0):
          labelTorch = torch.from_numpy(label)
          
        maskTorch = torch.tensor([1])
        if(len(mask) > 0):
          maskTorch = torch.from_numpy(mask)
          
          
        return {'image': torch.from_numpy(image),
                'label': labelTorch,
                'mask': maskTorch,
                'landmarks': landmarkData}

class SmoothImage(object):

    def __call__(self, sample):
      image, label, mask, landmarkData = sample['image'], sample['label'], sample['mask'], sample['landmarks']

      for i in range(0,image.shape[0]):
        imgToSmooth = image[i,]
        image[i,] = Utils.smoothArray3D(imgToSmooth, image.device, 1, 0.5, 3)

      return {'image': image,
                'label': label,
                'mask': mask,
                'landmarks': landmarkData}               
        