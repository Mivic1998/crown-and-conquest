# Testing and Validation

## Table of Contents

- [Testing and Validation](#testing-and-validation)
- [CSS Validation](#css-validation)
- [HTML Validation](#html-validation)
- [JavaScript Validation](#javascript-validation)
- [Python Validation](#python-validation)
- [Automated Django Testing](#automated-django-testing)
- [Lighthouse Validation](#lighthouse-validation)
  - [Lighthouse Score Reference](#lighthouse-score-reference)
  - [Lighthouse Results Summary](#lighthouse-results-summary)
- [Functional Testing](#functional-testing)
- [Responsive Testing](#responsive-testing)
- [Bugs Encountered and Fixed](#bugs-encountered-and-fixed)
- [Known Issues](#known-issues)
- [Conclusion](#conclusion)

# Testing and Validation

This document outlines the testing and validation processes undertaken throughout the development of **Crown & Conquest**.

Testing formed a continuous part of the development process rather than being reserved solely for the end of implementation. As new gameplay systems were introduced, each feature was validated to ensure that functionality remained consistent, existing behaviour was not unintentionally affected, and the application continued to provide a stable user experience across supported devices.

Given the complexity of the project, multiple complementary testing techniques were employed throughout development. These included automated Django testing, code validation, browser-based performance analysis, manual functional testing, responsive testing, and compatibility testing.

The testing process included:

- HTML validation using the W3C Nu HTML Checker
- CSS validation using the W3C CSS Validation Service
- JavaScript validation using ESLint
- Python validation using Ruff and Django's compileall utility
- Automated Django unit testing covering models, forms, views, business logic, and permissions
- Lighthouse performance, accessibility, best practices, and SEO analysis
- Manual functional testing across all major gameplay systems
- Responsive testing across desktop, tablet, and mobile layouts

Together, these testing approaches provide confidence that Crown & Conquest behaves consistently across its various gameplay systems while adhering to modern web standards and good software engineering practices.

---

# CSS Validation

CSS validation was performed using the **W3C CSS Validation Service** to ensure that the project's stylesheets conform to current CSS standards and contain no syntax errors.

Rather than distributing styling across numerous files, Crown & Conquest uses two primary stylesheets. The main `style.css` file provides the application's shared design system, typography, responsive layouts, reusable components, navigation, premium pages, warfare interfaces, event pages, and supporting UI elements. A separate `dashboard.css` stylesheet contains additional styling specific to the kingdom dashboard and its interactive components.

Following completion of development, both stylesheets were submitted to the W3C CSS Validator.

### Primary Stylesheet Validation

The primary stylesheet successfully passed validation with no errors reported.

![Primary CSS Validation](testing/main-css-validation.PNG)

### Dashboard Stylesheet Validation

The dashboard stylesheet also successfully passed validation with no errors reported.

![Dashboard CSS Validation](testing/dashboard-css-validation.PNG)

Successful validation confirms that both stylesheets are syntactically correct and conform to current CSS standards, helping to ensure consistent rendering across modern browsers while supporting the application's responsive design.

# HTML Validation

HTML validation was carried out using the **W3C Nu HTML Checker** to ensure that each template conforms to current HTML5 standards and follows good semantic structure.

As Crown & Conquest consists of numerous templates spanning authentication, kingdom management, diplomacy, warfare, premium functionality, and supporting informational pages, every user-facing page was individually validated following completion of development.

The following pages were successfully validated:

- Home
- Home (Logged Out)
- Login
- Register
- Dashboard
- Create Kingdom
- Kingdom Detail
- Statistics
- Leaderboard
- Turn History
- Turn Feedback
- Turn Report
- Event History
- Event Response
- Event Report
- Diplomacy
- Battle Report
- War History
- War Pending
- Declare War
- War Declaration Received
- Premium
- Settings
- Game Mechanics
- Logout

During development, several minor validation warnings were identified relating to semantic page structure and form accessibility. These were resolved by ensuring appropriate heading hierarchy, improving form markup, and refining template structure before the final validation process.

Following these refinements, every page returned a clean validation result with **no errors or warnings**.

The following screenshots provide evidence of the completed validation process.

### Home Page

The homepage was successfully validated using the W3C Nu HTML Checker with no errors reported.

![Home Validation](testing/home-html-validation.PNG)

The logged-out version of the homepage was also validated separately to ensure that conditional content rendered correctly.

![Home Logged Out Validation](testing/home-logged-out-html-validation.PNG)

---

### Authentication Pages

The login page successfully passed HTML validation with no issues identified.

![Login Validation](testing/login-html-validation.PNG)

The registration page was also validated successfully, confirming that all form elements conform to HTML5 standards.

![Register Validation](testing/create-account-html-validation.PNG)

---

### Kingdom Management Pages

The dashboard validated successfully, demonstrating that dynamic kingdom information is rendered using valid semantic HTML.

![Dashboard Validation](testing/dashboard-html-validation.PNG)

The Create Kingdom page passed validation, confirming that the kingdom creation form is correctly structured.

![Create Kingdom Validation](testing/create-kingdom-html-validation.PNG)

The Kingdom Detail page validated successfully with no HTML errors detected.

![Kingdom Detail Validation](testing/kingdom-detail-html-validation.PNG)

The Statistics page also passed validation while presenting dynamically generated statistical information.

![Statistics Validation](testing/statistics-html-validation.PNG)

The Leaderboard page validated successfully, confirming that ranking data is displayed using valid HTML markup.

![Leaderboard Validation](testing/html-leaderboard-validation.PNG)

---

### Turn and Event Pages

The Turn History page successfully passed HTML validation.

![Turn History Validation](testing/turn-history-html-validation.PNG)

The Turn Feedback page also validated successfully with no issues identified.

![Turn Feedback Validation](testing/turn-feedback-html-validation.PNG)

The Turn Report page passed validation, confirming the structure of the dynamically generated report.

![Turn Report Validation](testing/turn-report-html.PNG)

The Event History page validated successfully, ensuring historical event records are presented using valid HTML.

![Event History Validation](testing/event-history-html-validation.PNG)

The Event Response page passed validation, confirming that the AI response interface is correctly structured.

![Event Response Validation](testing/event-response-html-validation.PNG)

The Event Report page also successfully passed HTML validation.

![Event Report Validation](testing/event-report-html-validation.PNG)

---

### Warfare Pages

The Diplomacy page validated successfully while displaying interactive kingdom information.

![Diplomacy Validation](testing/diplomacy-html-validation.PNG)

The Battle Report page passed validation with no HTML errors reported.

![Battle Report Validation](testing/battle-report-html-validation.PNG)

The War History page also successfully validated.

![War History Validation](testing/war-history-html-validation.PNG)

The War Pending page passed validation, confirming the correctness of its dynamic content.

![War Pending Validation](testing/war-pending-html-validation.PNG)

The Declare War page also validated successfully, confirming that the declaration form conforms to HTML5 standards.

![Declare War Validation](testing/declare-war-html-validation.PNG)

The War Declaration Received page successfully passed HTML validation.

![War Declaration Received Validation](testing/war-declaration-received-html-validation.PNG)

---

### Premium and Account Pages

The Premium Membership page successfully passed HTML validation.

![Premium Validation](testing/premium-html-validation.PNG)

The Kingdom Settings page validated successfully, confirming that all account management forms are correctly structured.

![Settings Validation](testing/kingdom-settings-html-validation.PNG)

The Logout confirmation page also passed HTML validation.

![Logout Validation](testing/logout-html-validation.PNG)

---

### Supporting Pages

The Game Mechanics page successfully passed HTML validation, confirming that the informational content is presented using valid semantic HTML.

![Mechanics Validation](testing/mechanics-html-validation.PNG)

Collectively, these validation results confirm that the application's templates conform to modern HTML standards while providing a strong semantic foundation for accessibility, browser compatibility, and maintainability.

---

# JavaScript Validation

JavaScript validation was performed using both **ESLint** and **JSHint** to ensure that the project's client-side code follows modern JavaScript standards while remaining free from syntax errors and potential maintainability issues.

JavaScript is used throughout Crown & Conquest to enhance the user experience through interactive dashboards, responsive navigation, client-side validation, countdown timers, asynchronous requests, and other dynamic interface components.

## ESLint Validation

The project's JavaScript was first analysed using ESLint. This modern linter identified no remaining errors or warnings following development, confirming that the application's JavaScript adheres to current best practices.

**ESLint Validation Result**

- No errors found.
- No warnings found.

The screenshot below shows the successful ESLint validation.

![ESLint Validation](testing/js/eslint-js-validation.PNG)

## JSHint Validation

As an additional validation step, the project's JavaScript files were also analysed using JSHint.

The resulting warnings relate exclusively to modern ES6+ language features, including `const` declarations, template literals, arrow functions, and `for...of` loops. These warnings occur because JSHint defaults to ES5 compatibility unless configured with `esversion: 6`.

Other reported warnings are stylistic recommendations, such as the use of `new` for Bootstrap component initialisation or function declarations within blocks. These are expected behaviours within the project and do not represent functional errors.

No JSHint warnings indicated defects or prevented the application from functioning correctly across supported browsers.

### Dashboard JavaScript

The dashboard JavaScript validated successfully, with warnings relating only to modern ES6 syntax.

![Dashboard JSHint](testing/js/jshint-dashboard.PNG)

### Statistics JavaScript

The statistics page JavaScript also produced only ES6 compatibility warnings.

![Statistics JSHint](testing/js/jshint-statistics.PNG)

### War Countdown JavaScript

The war countdown script validated successfully, with warnings limited to ES6 syntax and stylistic recommendations.

![War Countdown JSHint](testing/js/jshint-war-countdown.PNG)

### War Notification JavaScript

The notification script similarly produced only ES6 compatibility warnings associated with modern JavaScript features such as arrow functions and `const` declarations.

![War Notification JSHint](testing/js/jshint-war-notification.PNG)

Using both ESLint and JSHint provided confidence that the application's client-side code is both syntactically correct and compliant with modern JavaScript development practices while remaining compatible with current browser environments.

---

Server-side gameplay logic, simulation calculations, AI processing, and database operations are implemented within Django using Python and are therefore validated separately in the following section.

# Python Validation

Python code quality was verified throughout development using **Ruff**, a modern static analysis and linting tool designed to identify syntax issues, unused imports, formatting inconsistencies, and other potential code quality concerns.

Regular linting ensured that the codebase remained consistent and maintainable as additional gameplay systems were introduced, helping to identify minor issues before they became larger implementation problems.

Following the completion of development, the project successfully passed Ruff validation with no remaining errors requiring correction.

The following screenshot shows the completed Ruff validation.

![Ruff Validation](testing/django/ruff.PNG)

In addition to linting, Django's Python modules were verified using the `compileall` utility. This process compiles every Python source file into bytecode, confirming that each module is syntactically valid and can be successfully interpreted by Python.

Successful completion of the compilation process provides additional confidence that no syntax errors remain within the project's Python source code.

The following screenshot shows the successful compilation results.

![Python Compileall Validation](testing/django/python-compileall.PNG)

Together, Ruff and `compileall` provide complementary validation by confirming both code quality and syntactic correctness across the application's Python codebase.

---

# Automated Django Testing

In addition to comprehensive manual testing, Crown & Conquest includes an extensive automated Django test suite covering the application's core business logic, models, forms, views, permissions, gameplay mechanics, and premium subscription functionality.

Rather than focusing solely on page rendering, the automated tests verify that the application's underlying systems behave correctly under both expected and exceptional conditions. External services such as Google's Gemini API and Stripe are mocked where appropriate, ensuring that the test suite remains deterministic, repeatable, and independent of third-party services.

The automated test suite is organised across the project's four primary Django applications:

- Core application
- Kingdom management
- Warfare and diplomacy
- Premium subscriptions and Stripe integration

Before executing the automated tests, Django's built-in system check framework was used to verify that the project configuration contained no configuration or model issues.

![Django System Check](testing/django/django-check.PNG)

The successful system check confirmed that no configuration errors, model inconsistencies, or deployment issues were identified before running the automated test suite.

---

## Core Application Tests

The core test suite verifies functionality shared across the application, ensuring that public pages, navigation, account management, and leaderboard functionality behave as expected.

Automated tests cover areas including:

- homepage rendering
- mechanics page accessibility
- leaderboard ranking calculations
- kingdom detail pages
- account deletion
- success and error messaging
- URL routing

These tests help ensure that the application's shared functionality continues to operate correctly as additional gameplay features are introduced.

![Core Test Suite](testing/django/core-test.PNG)

The core application test suite completed successfully, with all tests passing.

---

## Kingdom Management Tests

The Kingdom application contains the majority of the simulation's core gameplay logic and therefore includes the project's largest collection of automated tests.

The test suite verifies:

- Kingdom model behaviour
- leaderboard score calculations
- turn limit management
- daily turn reset logic
- premium turn allowances
- dashboard rendering
- kingdom creation and deletion
- settings management
- policy allocation forms
- turn history isolation
- statistics calculations
- authentication and ownership restrictions

Testing these systems ensures that the simulation behaves consistently while preventing invalid gameplay states and protecting player data.

![Kingdom Test Suite](testing/django/kingdoms-test.PNG)

The Kingdom application test suite completed successfully, with all tests passing.

---

## Warfare and Diplomacy Tests

The warfare application introduces significantly more complex gameplay interactions involving diplomacy, AI-assisted warfare, battle calculations, cooldowns, and permission handling.

Automated tests verify:

- war declaration workflow
- diplomacy filtering
- battle outcome calculations
- rallying cry validation
- AI-assisted defender responses
- battle reports
- war history
- cooldown management
- battle momentum calculations
- access permissions
- ownership restrictions
- war resolution

External AI requests are mocked during testing, allowing gameplay logic to be validated without requiring live Gemini API requests.

![Warfare Test Suite](testing/django/wars-test.PNG)

The warfare application test suite completed successfully, with all tests passing.

---

## Premium Subscription and Stripe Tests

Premium functionality is supported through a dedicated suite of automated tests covering both customer-facing subscription workflows and server-side Stripe webhook processing.

The test suite verifies:

- pricing page access
- checkout session creation
- authentication requirements
- premium subscription activation
- subscription cancellation
- premium status synchronisation
- turn limit updates
- webhook event handling
- webhook signature validation
- invalid webhook requests
- payment utility functions

Stripe API requests are mocked throughout testing, allowing the complete subscription workflow to be verified without creating real subscriptions or making external network requests.

![Payments Test Suite](testing/django/payments-test.PNG)

The payments application test suite completed successfully, with all tests passing.

---

Collectively, the automated Django test suite provides confidence that the application's business logic, gameplay systems, permissions, premium functionality, and external integrations behave consistently while reducing the likelihood of regressions during future development.

# Lighthouse Validation

Performance, Accessibility, Best Practices, and SEO testing was conducted using **Google Lighthouse** within Chrome DevTools. Testing was performed on the deployed application in both **desktop** and **mobile** modes to provide a realistic assessment of user experience across different device types.

As Crown & Conquest contains a mixture of static content, data-driven dashboards, AI-powered gameplay, and authenticated user functionality, Lighthouse testing was carried out across representative pages from each major area of the application.

---

## Lighthouse Score Reference

| Category | Score Range | Indicator | Explanation |
|----------|------------|-----------|-------------|
| Performance | 90–100 | 🟢 | Fast loading and efficient runtime performance |
| Performance | 50–89 | 🟠 | Moderate performance with opportunities for optimisation |
| Performance | 0–49 | 🔴 | Poor performance requiring significant optimisation |
| Accessibility | 90–100 | 🟢 | Content is accessible to the majority of users |
| Best Practices | 90–100 | 🟢 | Follows modern development and security practices |
| SEO | 90–100 | 🟢 | Well optimised for search engine visibility |

---

# Lighthouse Results Summary

The following sections summarise Lighthouse testing across the application’s principal pages. Reports were generated for both desktop and mobile environments wherever suitable, allowing performance, accessibility, best practices, and SEO to be assessed across different screen sizes.

The results showed a consistent pattern throughout the application. Accessibility and Best Practices were generally very strong, while SEO remained high across most pages. Performance scores were more variable, particularly on pages containing large background images, decorative artwork, charts, dynamic reports, or multiple interface components.

---

## Home Page

The Home page introduces Crown & Conquest through prominent hero artwork, promotional content, and explanations of the principal gameplay systems. Its image-heavy presentation contributes to a larger initial page load than simpler informational pages.

### Desktop

The following report shows the Lighthouse results for the authenticated desktop version of the Home page.

![Home Desktop Lighthouse](testing/lighthouse/home-desktop.PNG)

The logged-out Home page was tested separately because it presents different navigation options and introductory actions.

![Home Logged Out Desktop Lighthouse](testing/lighthouse/home-logged-out-desktop.PNG)

### Mobile

The following report shows the Lighthouse results for the authenticated mobile version of the Home page.

![Home Mobile Lighthouse](testing/lighthouse/home-mobile.PNG)

The logged-out mobile version was also tested to confirm that its conditional content remains accessible and responsive on smaller screens.

![Home Logged Out Mobile Lighthouse](testing/lighthouse/home-logged-out-mobile.PNG)

The Home page maintained strong Accessibility, Best Practices, and SEO results. Performance was affected by the large hero imagery and decorative assets used to establish the project’s medieval visual identity.

---

## Authentication Pages

Authentication pages were tested separately because they provide the principal entry points for new and returning users.

### Login Page

The Login page contains a focused authentication form together with links to account registration and external authentication options.

#### Desktop

The following report shows the Lighthouse results for the Login page in desktop mode.

![Login Desktop Lighthouse](testing/lighthouse/login-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Login page in mobile mode.

![Login Mobile Lighthouse](testing/lighthouse/login-mobile.PNG)

The Login page remained accessible and structurally sound across both device categories, although shared site imagery and external resources continued to affect raw performance scores.

---

### Register Page

The Register page allows new users to create an account before entering the kingdom creation workflow.

#### Desktop

The following report shows the Lighthouse results for the Register page in desktop mode.

![Register Desktop Lighthouse](testing/lighthouse/create-account-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Register page in mobile mode.

![Register Mobile Lighthouse](testing/lighthouse/create-account-mobile.PNG)

The registration form maintained strong Accessibility and Best Practices results on both desktop and mobile devices.

---

## Kingdom Management Pages

The kingdom management pages contain the principal simulation interfaces and therefore generally render more data and visual components than the public pages.

### Dashboard

The Dashboard is one of the most complex pages within the application, combining live kingdom statistics, policy controls, notifications, turn information, strategic actions, and decorative imagery.

#### Desktop

The following report shows the Lighthouse results for the Dashboard in desktop mode.

![Dashboard Desktop Lighthouse](testing/lighthouse/dashboard-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Dashboard in mobile mode.

![Dashboard Mobile Lighthouse](testing/lighthouse/dashboard-mobile.PNG)

The Dashboard’s performance score reflects the quantity of dynamic content and visual elements displayed simultaneously. Accessibility and Best Practices nevertheless remained consistently strong.

---

### Create Kingdom

The Create Kingdom page is the first authenticated gameplay page presented to a new player and contains the application’s principal kingdom creation form.

#### Desktop

The following report shows the Lighthouse results for the Create Kingdom page in desktop mode.

![Create Kingdom Desktop Lighthouse](testing/lighthouse/create-kingdom-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Create Kingdom page in mobile mode.

![Create Kingdom Mobile Lighthouse](testing/lighthouse/create-kingdom-mobile.PNG)

The page remained responsive and accessible despite containing multiple form controls, guidance text, and decorative artwork.

---

### Kingdom Detail

The Kingdom Detail page presents public strategic information relating to an individual kingdom.

#### Desktop

The following report shows the Lighthouse results for the Kingdom Detail page in desktop mode.

![Kingdom Detail Desktop Lighthouse](testing/lighthouse/kingdom-detail-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Kingdom Detail page in mobile mode.

![Kingdom Detail Mobile Lighthouse](testing/lighthouse/kingdom-detail-mobile.PNG)

As a comparatively focused data page, Kingdom Detail produced reliable Lighthouse results while maintaining clear presentation across screen sizes.

---

### Statistics

The Statistics page presents historical trends, numerical summaries, and chart-based kingdom analysis.

#### Desktop

The following report shows the Lighthouse results for the Statistics page in desktop mode.

![Statistics Desktop Lighthouse](testing/lighthouse/statistics-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Statistics page in mobile mode.

![Statistics Mobile Lighthouse](testing/lighthouse/statistics-mobile.PNG)

Rendering historical datasets and chart components increased the page’s processing and display requirements. However, Accessibility and Best Practices remained strong across both reports.

---

### Leaderboard

The Leaderboard displays dynamically calculated rankings for participating kingdoms.

#### Desktop

The following report shows the Lighthouse results for the Leaderboard in desktop mode.

![Leaderboard Desktop Lighthouse](testing/lighthouse/leaderboard-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Leaderboard in mobile mode.

![Leaderboard Mobile Lighthouse](testing/lighthouse/leaderboard-mobile.PNG)

The page continued to present dynamic ranking information clearly across device sizes, with performance influenced by the number of kingdom records and decorative crest assets being rendered.

---

## Turn and Event Pages

Turn and event pages display historical records, AI-assisted decisions, and detailed simulation reports. These pages often contain larger volumes of text and dynamically generated information.

### Turn History

The Turn History page provides a chronological record of previous kingdom turns.

#### Desktop

The following report shows the Lighthouse results for the Turn History page in desktop mode.

![Turn History Desktop Lighthouse](testing/lighthouse/turn-history-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Turn History page in mobile mode.

![Turn History Mobile Lighthouse](testing/lighthouse/turn-history-mobile.PNG)

The page remained readable and accessible despite the potentially large quantity of historical records presented.

---

### Turn Report

The Turn Report page explains the statistical consequences of a completed simulation turn.

#### Desktop

The following report shows the Lighthouse results for the Turn Report page in desktop mode.

![Turn Report Desktop Lighthouse](testing/lighthouse/turn-report-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Turn Report page in mobile mode.

![Turn Report Mobile Lighthouse](testing/lighthouse/turn-report-mobile.PNG)

The report layout maintained strong semantic structure and responsive presentation while displaying a substantial amount of generated gameplay information.

---

### Event History

The Event History page preserves a permanent record of previously resolved kingdom events.

#### Desktop

The following report shows the Lighthouse results for the Event History page in desktop mode.

![Event History Desktop Lighthouse](testing/lighthouse/event-history-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Event History page in mobile mode.

![Event History Mobile Lighthouse](testing/lighthouse/event-history-mobile.PNG)

Historical event data remained accessible across both device categories, although longer records naturally increase the amount of content rendered.

---

### Event Response

The Event Response page combines event artwork, scenario text, form controls, and AI-assisted decision submission.

#### Desktop

The following report shows the Lighthouse results for the Event Response page in desktop mode.

![Event Response Desktop Lighthouse](testing/lighthouse/event-response-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Event Response page in mobile mode.

![Event Response Mobile Lighthouse](testing/lighthouse/event-response-mobile.PNG)

The page’s performance score reflects the use of event imagery and multiple interactive components. Accessibility and Best Practices remained strong.

---

### Event Report

The Event Report page records the player’s response, Gemini evaluation, and resulting changes to the kingdom.

#### Desktop

The following report shows the Lighthouse results for the Event Report page in desktop mode.

![Event Report Desktop Lighthouse](testing/lighthouse/event-report-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Event Report page in mobile mode.

![Event Report Mobile Lighthouse](testing/lighthouse/event-report-mobile.PNG)

The detailed report remained readable and well structured despite combining dynamically generated narrative, feedback, and statistical outcomes.

---

## Warfare Pages

Warfare pages contain interactive forms, timers, battle information, reports, and kingdom artwork. Their performance scores therefore reflect a comparatively complex authenticated workflow.

### Diplomacy

The Diplomacy page presents eligible opponent kingdoms and allows players to begin the warfare process.

#### Desktop

The following report shows the Lighthouse results for the Diplomacy page in desktop mode.

![Diplomacy Desktop Lighthouse](testing/lighthouse/diplomacy-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Diplomacy page in mobile mode.

![Diplomacy Mobile Lighthouse](testing/lighthouse/diplomacy-mobile.PNG)

Dynamic opponent filtering, kingdom crest imagery, and strategic information increased page complexity while preserving strong accessibility.

---

### Declare War

The Declare War page contains opponent details and the rallying-cry form used to initiate a conflict.

#### Desktop

The following report shows the Lighthouse results for the Declare War page in desktop mode.

![Declare War Desktop Lighthouse](testing/lighthouse/declare-war-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Declare War page in mobile mode.

![Declare War Mobile Lighthouse](testing/lighthouse/declare-war-mobile.PNG)

The page remained responsive and accessible while combining dynamic kingdom information with validated user input.

---

### War Pending

The War Pending page displays conflicts that are awaiting a defender response or battle resolution.

#### Desktop

The following report shows the Lighthouse results for the War Pending page in desktop mode.

![War Pending Desktop Lighthouse](testing/lighthouse/war-pending-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the War Pending page in mobile mode.

![War Pending Mobile Lighthouse](testing/lighthouse/war-pending-mobile.PNG)

The page maintained clear responsive presentation while displaying live war state and timing information.

---

### War Notification

The War Notification page informs a defending player that another kingdom has initiated a conflict.

#### Desktop

The following report shows the Lighthouse results for the War Notification page in desktop mode.

![War Notification Desktop Lighthouse](testing/lighthouse/war-notification-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the War Notification page in mobile mode.

![War Notification Mobile Lighthouse](testing/lighthouse/war-notification-mobile.PNG)

The page combines opponent details, countdown functionality, narrative content, and a response form, resulting in higher rendering requirements than simpler pages.

---

### Battle Report

The Battle Report page presents the final outcome of a resolved conflict, including military strength, losses, and narrative reporting.

#### Desktop

The following report shows the Lighthouse results for the Battle Report page in desktop mode.

![Battle Report Desktop Lighthouse](testing/lighthouse/battle-report-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Battle Report page in mobile mode.

![Battle Report Mobile Lighthouse](testing/lighthouse/battle-report-mobile.PNG)

The report remained accessible and visually organised despite containing a large quantity of generated battle information.

---

### War History

The War History page provides a permanent record of previous conflicts involving the player’s kingdom.

#### Desktop

The following report shows the Lighthouse results for the War History page in desktop mode.

![War History Desktop Lighthouse](testing/lighthouse/war-history-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the War History page in mobile mode.

![War History Mobile Lighthouse](testing/lighthouse/war-history-mobile.PNG)

Historical records continued to display correctly across both environments, with performance varying according to the amount of stored conflict data.

---

## Premium and Account Pages

Premium and account pages combine authenticated forms, subscription information, and conditional interface content.

### Premium Membership

The Premium Membership page explains subscription benefits and begins the Stripe Checkout workflow.

#### Desktop

The following report shows the Lighthouse results for the Premium Membership page in desktop mode.

![Premium Desktop Lighthouse](testing/lighthouse/premium-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Premium Membership page in mobile mode.

![Premium Mobile Lighthouse](testing/lighthouse/premium-mobile.PNG)

Performance was affected by large promotional artwork and supporting visual content. Stripe processing itself occurs after the user leaves the page and therefore was not the principal source of the initial page-load cost.

---

### Settings

The Settings page allows users to edit kingdom information and, where available, premium appearance options.

#### Desktop

The following report shows the Lighthouse results for the Settings page in desktop mode.

![Settings Desktop Lighthouse](testing/lighthouse/settings-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Settings page in mobile mode.

![Settings Mobile Lighthouse](testing/lighthouse/settings-mobile.PNG)

The form-based interface remained accessible and usable across both tested environments.

---

### Logout Page

The Logout page provides a clear confirmation step before ending the authenticated session.

#### Desktop

The following report shows the Lighthouse results for the Logout page in desktop mode.

![Logout Desktop Lighthouse](testing/lighthouse/logout-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Logout page in mobile mode.

![Logout Mobile Lighthouse](testing/lighthouse/logout-mobile.PNG)

As a relatively lightweight account page, Logout produced stable results while maintaining the application’s shared visual design.

---

## Supporting Pages

In addition to the application's core gameplay systems, Lighthouse testing was performed on supporting informational pages. Although these pages are less interactive than the dashboard or simulation interfaces, they remain an important part of the overall user experience and were evaluated to ensure they maintain strong accessibility, usability, and search engine optimisation standards.

### Game Mechanics

The Game Mechanics page explains the principal economic, military, event, and progression systems available within Crown & Conquest.

#### Desktop

The following report shows the Lighthouse results for the Game Mechanics page in desktop mode.

![Mechanics Desktop Lighthouse](testing/lighthouse/mechanics-desktop.PNG)

#### Mobile

The following report shows the Lighthouse results for the Game Mechanics page in mobile mode.

![Mechanics Mobile Lighthouse](testing/lighthouse/mechanics-mobile.PNG)

Although primarily informational, the page contains several large illustrations and extensive content, which increased page weight while maintaining strong Accessibility, Best Practices, and SEO results.

---

## Performance Considerations and Impact

Lighthouse testing showed that **Accessibility** and **Best Practices** remained consistently strong throughout Crown & Conquest, while SEO scores also remained high across the tested pages. The principal area requiring further improvement is **Performance**, which varied considerably according to page content and device simulation.

Several factors contributed to the measured performance results:

- **Image-heavy presentation:** Large hero banners, event illustrations, battle artwork, crests, icons, and decorative backgrounds are used throughout the application to establish its medieval-fantasy identity. These assets increase transfer size and can delay Largest Contentful Paint.
- **Oversized image delivery:** Some artwork may be served at dimensions greater than those required by the rendered viewport, meaning mobile users may download larger files than necessary.
- **Authenticated page complexity:** The Dashboard, Statistics, Event, and Warfare pages render multiple cards, tables, notifications, forms, and conditional sections within a single request.
- **Chart rendering:** The Statistics page includes client-side chart rendering, which introduces additional JavaScript execution and layout work.
- **Shared CSS:** The application loads a substantial global stylesheet containing rules for many different pages. This simplifies design consistency but may result in unused CSS being transferred for individual routes.
- **External fonts and libraries:** Google Fonts, Bootstrap, icons, and other external resources introduce additional requests and may delay text rendering if not already cached.
- **Heroku response latency:** Testing was conducted against the deployed Heroku application. Server location, dyno state, network conditions, and database response time can influence Time to First Byte.
- **Mobile throttling:** Lighthouse mobile mode simulates reduced processing power and slower network conditions, which explains why mobile Performance scores were often lower than desktop results.
- **Headless authenticated testing:** Authenticated reports were generated programmatically through Puppeteer and Lighthouse. This ensured repeatable access to protected pages but may produce slightly different timing results from manual browser testing.
- **Long historical pages:** Turn History, Event History, and War History can render increasing quantities of stored records as gameplay progresses.

The lower Performance scores do not indicate broken functionality, but they highlight realistic opportunities for optimisation.

Potential future improvements include:

- converting suitable images to WebP or AVIF;
- generating separate desktop, tablet, and mobile image sizes;
- using `srcset` and `sizes` to deliver appropriately scaled assets;
- lazy loading non-critical images below the fold;
- preloading only the most important hero image and font resources;
- defining image dimensions to reduce layout shifts;
- compressing decorative images more aggressively;
- splitting page-specific CSS and JavaScript where practical;
- deferring scripts that are not required for the initial render;
- reducing or paginating long historical datasets;
- reviewing Lighthouse diagnostics for unused CSS and render-blocking resources;
- applying stronger static-file caching and compression in production.

Further optimisation would need to balance measured performance against the visual identity and immersive presentation that form an important part of the Crown & Conquest user experience.

# Functional Testing

Functional testing was carried out continuously throughout development to verify that individual features behaved correctly and that newly implemented functionality did not introduce regressions elsewhere within the application.

Testing covered all major gameplay systems, including authentication, kingdom management, turn progression, dynamic events, warfare, premium membership, and account management.

The following areas were tested manually throughout development:

| Feature | Expected Behaviour | Result |
|----------|-------------------|--------|
| User Registration | New users can successfully create an account | ✅ Pass |
| User Login | Registered users can authenticate successfully | ✅ Pass |
| Kingdom Creation | Authenticated users can create a kingdom | ✅ Pass |
| Dashboard | Kingdom statistics display correctly | ✅ Pass |
| Turn Progression | Advancing a turn updates kingdom statistics correctly | ✅ Pass |
| Turn Limits | Daily turn allowances are enforced correctly | ✅ Pass |
| Event Generation | Eligible events are generated correctly | ✅ Pass |
| Event Response | Player responses are processed successfully | ✅ Pass |
| Event Reports | Completed reports display correctly | ✅ Pass |
| Kingdom Statistics | Historical statistics display correctly | ✅ Pass |
| Turn History | Previous turns are recorded correctly | ✅ Pass |
| Event History | Historical events remain accessible | ✅ Pass |
| Diplomacy | Eligible kingdoms can be selected for warfare | ✅ Pass |
| War Declaration | War requests are created successfully | ✅ Pass |
| War Notifications | Defending kingdoms receive notifications | ✅ Pass |
| Battle Resolution | Battles calculate correctly | ✅ Pass |
| Battle Reports | Completed reports display correctly | ✅ Pass |
| War History | Previous wars remain accessible | ✅ Pass |
| Leaderboard | Rankings update correctly | ✅ Pass |
| Premium Checkout | Stripe checkout session created successfully | ✅ Pass |
| Premium Membership | Premium features unlock correctly | ✅ Pass |
| Settings | Kingdom settings update successfully | ✅ Pass |
| Logout | Users can safely terminate their session | ✅ Pass |
| Account Deletion | Kingdom and account deletion require confirmation | ✅ Pass |

In addition to verifying expected behaviour, testing also confirmed that invalid actions were handled correctly, including attempting to access protected pages without authentication, declaring war against invalid targets, submitting invalid forms, and exceeding daily turn allowances.

Collectively, these manual tests confirmed that all major user journeys operate as intended.

---

# Responsive Testing

Responsive testing was carried out throughout development to ensure that Crown & Conquest remained fully usable across desktop, tablet, and mobile devices.

Particular attention was given to pages containing large quantities of strategic information, including the dashboard, statistics, diplomacy, and event interfaces, ensuring that content remained readable without sacrificing functionality.

Testing confirmed that the application adapts successfully across different viewport sizes.

| Device | Result |
|---------|--------|
| Desktop | ✅ Fully responsive |
| Laptop | ✅ Fully responsive |
| Tablet | ✅ Fully responsive |
| Mobile | ✅ Fully responsive |

Responsive testing confirmed that:

- navigation remains accessible across all screen sizes;
- dashboard cards stack appropriately on smaller devices;
- tables and reports remain readable;
- forms remain usable using touch controls;
- event pages adapt naturally to smaller screens;
- warfare interfaces remain fully functional on mobile devices.

Combined with the Lighthouse mobile testing results, these observations demonstrate that responsive behaviour has been implemented consistently throughout the application.

---

# Bugs Encountered and Fixed

As with any project of this size, several issues were identified throughout development and resolved prior to deployment.

Examples included:

- refinement of responsive layouts across smaller devices;
- adjustments to semantic HTML to eliminate validation warnings;
- improvements to form validation and error handling;
- refinement of gameplay calculations during turn progression;
- permission checks preventing unauthorised access to protected pages;
- improvements to warfare validation and cooldown handling;
- refinement of premium membership synchronisation following successful Stripe payments.

Each identified issue was investigated, corrected, and subsequently retested before development continued.

The inclusion of both automated Django tests and repeated manual testing helped reduce the likelihood of regressions as additional gameplay systems were introduced.

---

# Known Issues

At the time of submission, no known issues affecting the core functionality of the application remain.

Minor variations in Lighthouse performance scores occur between pages due to the differing complexity of individual interfaces. Pages containing larger quantities of dynamic content, authenticated data, or AI-generated information naturally require additional processing compared to static informational pages.

These differences are expected and do not affect the usability or reliability of the application.

---

# Conclusion

Testing was performed continuously throughout the development of Crown & Conquest using a combination of automated testing, manual testing, code validation, and browser-based analysis.

The completed testing process included:

- HTML validation
- CSS validation
- JavaScript validation
- Python validation
- Automated Django testing
- Lighthouse analysis
- Manual functional testing
- Responsive testing

Together, these testing methods provide confidence that the application behaves reliably across its major gameplay systems while adhering to modern web standards.

Overall, Crown & Conquest successfully passed validation across its front-end and back-end technologies, demonstrated consistent behaviour throughout extensive manual and automated testing, and provides a stable, responsive, and maintainable full-stack application.