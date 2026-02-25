import React, { useState, useEffect } from 'react';
import { FaSpinner, FaCheckCircle, FaExclamationCircle } from 'react-icons/fa';
import type { TaskStatus } from '../types/podcast';

interface StatusDisplayProps {
  status: TaskStatus;
  error?: string;
}

const STATUS_MESSAGES = [
  'מתחיל לעבוד על הפודקאסט...',
  'יוצר מבנה פודקאסט (Blueprint)...',
  'חוקר את הנושא...',
  'יוצר קווי מתאר מפורטים...',
  'כותב תסריט...',
  'ממיר טקסט לדיבור...',
  'משלים עיבוד...',
];

export const StatusDisplay: React.FC<StatusDisplayProps> = ({ status, error }) => {
  const [messageIndex, setMessageIndex] = useState(0);

  useEffect(() => {
    if (status !== 'processing') return;

    const interval = setInterval(() => {
      setMessageIndex((prev) => (prev + 1) % STATUS_MESSAGES.length);
    }, 3000); // Change message every 3 seconds

    return () => clearInterval(interval);
  }, [status]);

  if (status === 'completed') {
    return (
      <div className="bg-green-50 dark:bg-green-900 border-2 border-green-500 rounded-lg p-6 text-center">
        <FaCheckCircle className="text-green-500 dark:text-green-300 mx-auto mb-3" size={48} />
        <h3 className="text-xl font-semibold text-green-800 dark:text-green-200 mb-2">
          הפודקאסט מוכן! 🎉
        </h3>
        <p className="text-green-700 dark:text-green-300">
          הפודקאסט שלך נוצר בהצלחה וזמין להשמעה והורדה
        </p>
      </div>
    );
  }

  if (status === 'failed') {
    return (
      <div className="bg-red-50 dark:bg-red-900 border-2 border-red-500 rounded-lg p-6 text-center">
        <FaExclamationCircle className="text-red-500 dark:text-red-300 mx-auto mb-3" size={48} />
        <h3 className="text-xl font-semibold text-red-800 dark:text-red-200 mb-2">
          שגיאה ביצירת הפודקאסט
        </h3>
        <p className="text-red-700 dark:text-red-300">
          {error || 'אירעה שגיאה לא צפויה. אנא נסה שוב.'}
        </p>
      </div>
    );
  }

  // Processing status
  return (
    <div className="bg-blue-50 dark:bg-blue-900 border-2 border-blue-500 rounded-lg p-6 text-center">
      <FaSpinner className="text-blue-500 dark:text-blue-300 mx-auto mb-3 animate-spin" size={48} />
      <h3 className="text-xl font-semibold text-blue-800 dark:text-blue-200 mb-2">
        מעבד את הפודקאסט...
      </h3>
      <p className="text-blue-700 dark:text-blue-300 mb-4">
        {STATUS_MESSAGES[messageIndex]}
      </p>
      <div className="w-full bg-blue-200 dark:bg-blue-700 rounded-full h-2 overflow-hidden">
        <div className="bg-blue-500 dark:bg-blue-400 h-full animate-pulse" style={{ width: '60%' }} />
      </div>
      <p className="text-sm text-blue-600 dark:text-blue-400 mt-3">
        זה עשוי לקחת מספר דקות, אנא המתן...
      </p>
    </div>
  );
};
